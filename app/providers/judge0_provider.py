"""Existing Judge0 HTTP integration, retained behind the provider boundary.

No network calls happen until explicitly selected; this phase does not verify it.
The legacy instance exposes C rather than a guaranteed C17 compiler and no Java21.
"""
import httpx

from app.providers.judge_provider import ExecutionResult, JudgeProvider, JudgeRequest, Verdict


class Judge0Provider(JudgeProvider):
    name = "judge0"
    supported_languages = frozenset({"cpp", "c", "python"})
    language_ids = {"c": 50, "cpp": 54, "python": 71}

    def __init__(self, settings):
        self.settings = settings

    async def run(self, request: JudgeRequest) -> ExecutionResult:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.JUDGE0_API_KEY:
            headers["X-Auth-Token"] = self.settings.JUDGE0_API_KEY
        if self.settings.JUDGE0_API_HOST:
            headers["X-RapidAPI-Host"] = self.settings.JUDGE0_API_HOST
            if self.settings.JUDGE0_API_KEY:
                headers["X-RapidAPI-Key"] = self.settings.JUDGE0_API_KEY
        payload = {"source_code": request.source, "language_id": self.language_ids[request.language],
                   "stdin": request.stdin, "cpu_time_limit": max(1, min(request.time_limit_ms / 1000, 10)),
                   "memory_limit": request.memory_limit_kb, "enable_network": False}
        async with httpx.AsyncClient(timeout=self.settings.JUDGE0_TIMEOUT_SECONDS) as client:
            response = await client.post(self.settings.JUDGE0_URL.rstrip("/") + "/submissions?base64_encoded=false&wait=true",
                                         json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        label = (data.get("status") or {}).get("description", "")
        verdict = {
            "Accepted": Verdict.ACCEPTED, "Wrong Answer": Verdict.WRONG_ANSWER,
            "Compilation Error": Verdict.COMPILATION_ERROR, "Memory Limit Exceeded": Verdict.MEMORY_LIMIT_EXCEEDED,
        }.get(label, Verdict.INTERNAL_ERROR)
        if label.startswith("Runtime Error"):
            verdict = Verdict.RUNTIME_ERROR
        elif label.startswith("Time Limit Exceeded"):
            verdict = Verdict.TIME_LIMIT_EXCEEDED
        return ExecutionResult(verdict, data.get("stdout") or "", data.get("stderr") or "",
                               int(float(data["time"]) * 1000) if data.get("time") else None,
                               data.get("memory"), data.get("compile_output") or "")
