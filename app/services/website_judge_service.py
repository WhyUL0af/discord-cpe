"""Run/Submit orchestration independent of Judge0 transport and wire formats."""
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.models import Submission
from app.providers.judge_provider import JudgeProvider, JudgeRequest, TestCase, Verdict, LABELS, LANGUAGES
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.solved_repo import SolvedRepository
from app.services.website_problem_service import WebsiteProblemService

logger = logging.getLogger(__name__)


class CodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    code: str = Field(min_length=1, max_length=262144)
    input: str | None = Field(default=None, max_length=65536)
    input_mode: str = "auto"

    @field_validator("code")
    @classmethod
    def source_size(cls, value):
        if len(value.encode("utf-8")) > 256 * 1024:
            raise ValueError("Source must not exceed 256 KB")
        return value

    @field_validator("input_mode")
    @classmethod
    def valid_input_mode(cls, value):
        if value not in {"auto", "sample", "custom"}:
            raise ValueError("Invalid input mode")
        return value


def request_for(problem, payload, provider):
    if payload.language not in LANGUAGES or payload.language not in provider.supported_languages:
        raise HTTPException(422, "不支援的程式語言")
    custom = payload.input_mode == "custom" or (payload.input_mode == "auto" and bool(payload.input))
    stdin = (payload.input or "") if custom else problem.sample_input or ""
    return JudgeRequest(payload.code, payload.language, stdin, problem.time_limit or 3000,
                        problem.memory_limit or settings.JUDGE0_DEFAULT_MEMORY_LIMIT_KB,
                        problem.sample_input or "", problem.sample_output or "")


def clean_compiler_message(message):
    """Fail closed: keep diagnostics only, without echoed paths/source/commands/env."""
    diagnostics = []
    for line in message[:16384].splitlines():
        match = re.search(r"\b(error|warning|fatal error):\s*(.*)", line, re.I)
        if not match:
            continue
        detail = match.group(2)
        # Only known diagnostic categories, never arbitrary quoted source or secrets.
        categories = ("simulated compilation failure", "expected", "syntax", "undeclared", "not declared",
                      "undefined reference", "incompatible", "cannot find symbol", "illegal", "unclosed", "missing")
        category = next((c for c in categories if c in detail.lower()), None)
        if category:
            diagnostics.append(f"{match.group(1).lower()}: {category}")
    return "\n".join(diagnostics)[:2048] or ("Compilation failed. Check syntax and selected language." if message else "")


def submission_data(row, include_code=False):
    normalized = next((v.value for v, label in LABELS.items() if label == row.verdict), None)
    data = {"submission_id": row.id, "problem_id": row.problem_id, "status": row.status.lower(),
            "verdict": normalized, "result": row.verdict, "runtime_ms": row.runtime,
            "memory_kb": row.memory, "language": row.language, "passed_tests": row.passed_tests,
            "total_tests": row.total_tests, "compiler_message": clean_compiler_message(row.compiler_message or ""),
            "submitted_at": row.submitted_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "mock": row.judge_provider == "mock", "failure": json.loads(row.failure_details) if row.failure_details else None}
    if include_code:
        data["source_code"] = row.code or ""
    return data


class RunService:
    @staticmethod
    async def run(session, problem_id, payload, provider):
        problem = await WebsiteProblemService.get(session, problem_id)
        request = request_for(problem, payload, provider)
        try:
            result = await provider.run(request)
        except Exception:
            raise HTTPException(502, "Judge 執行失敗，請稍後重試") from None
        custom = payload.input_mode == "custom" or (payload.input_mode == "auto" and bool(payload.input))
        compiler = clean_compiler_message(result.compiler_message)
        return {"result": LABELS[result.verdict], "verdict": result.verdict.value, "status": "finished",
                "stdout": result.stdout[:65536], "stderr": "Execution failed." if result.stderr else "",
                "output": (result.stdout or compiler or ("Execution failed." if result.stderr else ""))[:65536],
                "input": request.stdin, "expected_output": "" if custom else problem.sample_output or "",
                "runtime_ms": result.runtime_ms, "memory_kb": result.memory_kb,
                "compiler_message": compiler, "mock": provider.development_only}


class WebsiteSubmissionService:
    @staticmethod
    async def create(session, user_id, problem_id, payload, provider):
        problem = await WebsiteProblemService.get(session, problem_id)
        request = request_for(problem, payload, provider)
        try:
            data = json.loads(problem.test_cases or "[]")
            if not isinstance(data, list) or not data:
                raise ValueError()
            cases = [TestCase(str(c["input"]), str(c["output"]), c.get("hidden", True) is not False) for c in data]
        except (ValueError, TypeError, KeyError):
            raise HTTPException(503, "此題尚未設定有效練習測資，目前只能 Run") from None
        row = Submission(user_id=user_id, problem_id=problem.id, source="website", code=payload.code,
                         language=LANGUAGES[payload.language]["label"], verdict="Pending", status="QUEUED",
                         judge_provider=provider.name, total_tests=len(cases))
        session.add(row)
        await session.flush()
        await session.commit()
        return row, request, cases

    @staticmethod
    async def process(factory, submission_id, request, cases, provider):
        async with factory() as session:
            row = await session.get(Submission, submission_id)
            if not row or row.status != "QUEUED":
                return
            row.status, row.verdict = "RUNNING", "Judging"
            row.started_at = datetime.now(timezone.utc)
            await session.commit()
        try:
            result = await provider.submit(request, cases)
        except Exception:
            # Do not log external response bodies, credentials or user source.
            logger.warning("Judge provider failed for submission %s", submission_id)
            from app.providers.judge_provider import JudgeResult
            result = JudgeResult(Verdict.INTERNAL_ERROR, total_tests=len(cases))
        async with factory() as session:
            row = await session.get(Submission, submission_id)
            if not row:
                return
            row.status, row.verdict = "FINISHED", LABELS[result.verdict]
            row.runtime, row.memory = result.runtime_ms, result.memory_kb
            row.passed_tests, row.total_tests = result.passed_tests, result.total_tests
            row.compiler_message = clean_compiler_message(result.compiler_message)
            row.finished_at = datetime.now(timezone.utc)
            # Enforce the visibility rule here as well as in the provider.
            failure = None
            candidate = result.public_failure
            if isinstance(candidate, dict):
                index = candidate.get("test_case")
                if type(index) is int and 1 <= index <= len(cases) and not cases[index - 1].hidden:
                    case = cases[index - 1]
                    failure = {"test_case": index, "input": case.stdin, "expected": case.expected_output,
                               "output": str(candidate.get("output", ""))[:8192]}
            row.failure_details = json.dumps(failure) if failure else None
            if result.verdict == Verdict.ACCEPTED:
                await SolvedRepository.record_solved(session, row.user_id, row.problem_id, row.submitted_at)
            await session.commit()

    @staticmethod
    async def owned(session, submission_id, user_id):
        row = await SubmissionRepository.get_owned(session, submission_id, user_id)
        if not row:
            raise HTTPException(404, "找不到提交")
        return row
