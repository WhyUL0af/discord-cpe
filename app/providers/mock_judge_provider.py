"""DEVELOPMENT/TEST ONLY. Simulates results; never interprets source code."""
import asyncio

from app.providers.judge_provider import ExecutionResult, JudgeProvider, JudgeRequest, JudgeResult, TestCase, Verdict


class MockJudgeProvider(JudgeProvider):
    name = "mock"
    development_only = True

    def __init__(self, verdict: Verdict = Verdict.ACCEPTED, delay: float = 0.3):
        self.verdict = Verdict(verdict)
        self.delay = max(0, delay)

    async def run(self, request: JudgeRequest) -> ExecutionResult:
        await asyncio.sleep(self.delay)
        output = request.sample_output if request.stdin == request.sample_input else "[Mock] Custom input received; source code was not executed.\n"
        return ExecutionResult(self.verdict, stdout=output if self.verdict == Verdict.ACCEPTED else "",
                               runtime_ms=12, memory_kb=4096, compiler_message=self._compiler_message())

    async def submit(self, request: JudgeRequest, cases: list[TestCase]) -> JudgeResult:
        await asyncio.sleep(self.delay)
        return JudgeResult(self.verdict, passed_tests=len(cases) if self.verdict == Verdict.ACCEPTED else 0,
                           total_tests=len(cases), runtime_ms=12, memory_kb=4096,
                           compiler_message=self._compiler_message())

    def _compiler_message(self):
        return "line 1: error: simulated compilation failure" if self.verdict == Verdict.COMPILATION_ERROR else ""
