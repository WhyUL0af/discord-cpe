"""Provider-neutral contracts. No user program executes in this application."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    ACCEPTED = "ACCEPTED"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


LABELS = {
    Verdict.ACCEPTED: "Accepted", Verdict.WRONG_ANSWER: "Wrong Answer",
    Verdict.TIME_LIMIT_EXCEEDED: "Time Limit Exceeded",
    Verdict.MEMORY_LIMIT_EXCEEDED: "Memory Limit Exceeded",
    Verdict.RUNTIME_ERROR: "Runtime Error", Verdict.COMPILATION_ERROR: "Compilation Error",
    Verdict.INTERNAL_ERROR: "Internal Error",
}
LANGUAGES = {
    "cpp": {"label": "C++17", "monaco": "cpp", "starter": "#include <iostream>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n"},
    "c": {"label": "C17", "monaco": "c", "starter": "#include <stdio.h>\n\nint main(void) {\n    return 0;\n}\n"},
    "python": {"label": "Python 3", "monaco": "python", "starter": "def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n"},
    "java": {"label": "Java 21", "monaco": "java", "starter": "public class Main {\n    public static void main(String[] args) {\n    }\n}\n"},
}


@dataclass(frozen=True)
class JudgeRequest:
    source: str
    language: str
    stdin: str
    time_limit_ms: int
    memory_limit_kb: int
    sample_input: str = ""
    sample_output: str = ""


@dataclass(frozen=True)
class TestCase:
    stdin: str
    expected_output: str
    hidden: bool = True


@dataclass
class ExecutionResult:
    verdict: Verdict
    stdout: str = ""
    stderr: str = ""
    runtime_ms: int | None = None
    memory_kb: int | None = None
    compiler_message: str = ""


@dataclass
class JudgeResult:
    verdict: Verdict
    passed_tests: int = 0
    total_tests: int = 0
    runtime_ms: int | None = None
    memory_kb: int | None = None
    compiler_message: str = ""
    public_failure: dict | None = None


class JudgeProvider(ABC):
    name: str
    development_only = False
    supported_languages = frozenset(LANGUAGES)

    @abstractmethod
    async def run(self, request: JudgeRequest) -> ExecutionResult:
        """Run sample/custom input without creating any submission."""

    async def submit(self, request: JudgeRequest, cases: list[TestCase]) -> JudgeResult:
        """Evaluate cases in the provider, returning only public failure data."""
        from dataclasses import replace
        result = JudgeResult(Verdict.ACCEPTED, total_tests=len(cases))
        for index, case in enumerate(cases, 1):
            execution = await self.run(replace(request, stdin=case.stdin))
            result.runtime_ms = max(result.runtime_ms or 0, execution.runtime_ms or 0)
            result.memory_kb = max(result.memory_kb or 0, execution.memory_kb or 0)
            result.verdict = execution.verdict
            result.compiler_message = execution.compiler_message
            if execution.verdict == Verdict.ACCEPTED:
                if execution.stdout.replace("\r\n", "\n").rstrip() != case.expected_output.replace("\r\n", "\n").rstrip():
                    result.verdict = Verdict.WRONG_ANSWER
            if result.verdict != Verdict.ACCEPTED:
                if not case.hidden:
                    result.public_failure = {"test_case": index, "input": case.stdin,
                                             "expected": case.expected_output, "output": execution.stdout[:8192]}
                break
            result.passed_tests += 1
        return result
