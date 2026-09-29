"""Seven-question notification sets; no local judge or contest database."""

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem import Problem
from app.providers.problem_provider import CpeProblemProvider
from app.repositories.problem_repo import ProblemRepository


BLUEPRINT = (1, 1, 2, 2, 3, 3, 4)
DURATION_MINUTES = 180
LEVEL_NAMES = {1: "基礎", 2: "中階", 3: "進階", 4: "挑戰"}


@dataclass(frozen=True)
class ExamCandidate:
    number: int
    level: int
    topic: str
    one_star: bool = False


def load_pool(path: Path | None = None) -> list[ExamCandidate]:
    path = path or Path(__file__).resolve().parents[1] / "data" / "mock_exam_pool.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    pool = [ExamCandidate(**row) for row in data["problems"]]
    if len({row.number for row in pool}) != len(pool):
        raise ValueError("模擬考題庫含重複題號。")
    if any(row.level not in LEVEL_NAMES or not row.topic for row in pool):
        raise ValueError("模擬考題庫難度或題型設定不正確。")
    return pool


def select_exam(pool: list[ExamCandidate], rng=None) -> list[ExamCandidate]:
    """Backtrack to satisfy difficulty, uniqueness and topic constraints."""
    rng = rng or random.SystemRandom()
    buckets = {level: [p for p in pool if p.level == level] for level in LEVEL_NAMES}
    for bucket in buckets.values():
        rng.shuffle(bucket)

    def search(chosen, topics):
        if len(chosen) == 7:
            return chosen if len(topics) >= 4 and any(p.one_star for p in chosen) else None
        for candidate in buckets[BLUEPRINT[len(chosen)]]:
            if any(p.number == candidate.number for p in chosen) or topics[candidate.topic] >= 2:
                continue
            updated = topics.copy()
            updated[candidate.topic] += 1
            result = search(chosen + [candidate], updated)
            if result:
                return result
        return None

    result = search([], Counter())
    if result is None:
        raise ValueError("題庫不足以組成 7 題：需 2 基礎、2 中階、2 進階、1 挑戰，至少 4 種題型及 1 題一星題。")
    return result


class MockExamService:
    def __init__(self, provider=None, pool=None):
        self.provider = provider or CpeProblemProvider()
        self.pool = load_pool() if pool is None else pool

    async def create_set(self, session: AsyncSession) -> list[tuple[ExamCandidate, Problem]]:
        result = []
        for candidate in select_exam(self.pool):
            # Resolve actual UVa metadata, including PID, before publishing.
            data = await self.provider.refresh_problem_metadata(candidate.number)
            if not data or not data.uhunt_pid:
                raise ValueError(f"無法向 uHunt 確認 UVa {candidate.number}，本次不發送題組，請稍後重試。")
            problem = await ProblemRepository.upsert_from_data(session, data)
            # Existing imports may carry an outdated PID; use the resolved official mapping.
            problem.uhunt_pid = data.uhunt_pid
            await session.flush()
            result.append((candidate, problem))
        return result
