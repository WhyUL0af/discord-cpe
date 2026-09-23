from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def get_problem_external_url(problem_number: int, uhunt_pid: Optional[int] = None) -> str:
    """Generate external URL for a UVa problem.

    Uses official UVa PDF problem statement link or show_problem link.
    """
    volume = problem_number // 100
    return f"https://onlinejudge.org/external/{volume}/{problem_number}.pdf"


class ProblemData:
    def __init__(
        self,
        problem_number: int,
        title: str,
        difficulty: Optional[str] = None,
        uhunt_pid: Optional[int] = None,
        source: str = "UVa Online Judge",
        external_url: Optional[str] = None,
        time_limit: Optional[int] = None,
    ) -> None:
        self.problem_number = problem_number
        self.title = title
        self.difficulty = difficulty
        self.uhunt_pid = uhunt_pid
        self.source = source
        self.external_url = external_url or get_problem_external_url(problem_number, uhunt_pid)
        self.time_limit = time_limit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_number": self.problem_number,
            "title": self.title,
            "difficulty": self.difficulty,
            "uhunt_pid": self.uhunt_pid,
            "source": self.source,
            "external_url": self.external_url,
            "time_limit": self.time_limit,
        }


class BaseProblemProvider(ABC):
    """Abstract Problem Provider."""

    @abstractmethod
    async def get_problem(self, problem_number: int) -> Optional[ProblemData]:
        pass

    @abstractmethod
    async def get_problems(self, difficulty: Optional[str] = None) -> List[ProblemData]:
        pass

    @abstractmethod
    async def get_random_problem(self, difficulty: Optional[str] = None) -> Optional[ProblemData]:
        pass

    @abstractmethod
    async def refresh_problem_metadata(self, problem_number: int) -> Optional[ProblemData]:
        pass


class CpeProblemProvider(BaseProblemProvider):
    """Problem provider backed by verified CPE dataset and uHunt metadata."""

    def __init__(self, dataset_path: Optional[str] = None) -> None:
        if dataset_path:
            self.dataset_path = Path(dataset_path)
        else:
            self.dataset_path = Path(__file__).resolve().parent.parent / "data" / "cpe_problems.json"
        self._dataset: Dict[int, ProblemData] = {}
        self._load_dataset()

    def _load_dataset(self) -> None:
        if not self.dataset_path.exists():
            logger.warning(f"CPE dataset not found at {self.dataset_path}")
            return

        try:
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                p_num = int(item["problem_number"])
                self._dataset[p_num] = ProblemData(
                    problem_number=p_num,
                    title=item["title"],
                    difficulty=item.get("difficulty"),
                    uhunt_pid=item.get("uhunt_pid"),
                    source=item.get("source", "UVa Online Judge"),
                    external_url=item.get("external_url"),
                    time_limit=item.get("time_limit"),
                )
            logger.info(f"Loaded {len(self._dataset)} CPE problems from dataset.")
        except Exception as e:
            logger.error(f"Failed to load CPE problems dataset: {e}", exc_info=True)

    async def get_problem(self, problem_number: int) -> Optional[ProblemData]:
        if problem_number in self._dataset:
            return self._dataset[problem_number]

        # If not in dataset, attempt to query uHunt metadata
        # (Difficulty will be Unknown since it's not in the verified CPE dataset)
        return await self.refresh_problem_metadata(problem_number)

    async def get_problems(self, difficulty: Optional[str] = None) -> List[ProblemData]:
        if difficulty:
            return [p for p in self._dataset.values() if p.difficulty == difficulty]
        return list(self._dataset.values())

    async def get_random_problem(self, difficulty: Optional[str] = None) -> Optional[ProblemData]:
        import random
        pool = await self.get_problems(difficulty=difficulty)
        if not pool:
            return None
        return random.choice(pool)

    async def refresh_problem_metadata(self, problem_number: int) -> Optional[ProblemData]:
        """Fetch problem metadata from uHunt API /p/num/{problem_number}."""
        url = f"{settings.UHUNT_BASE_URL.rstrip('/')}/p/num/{problem_number}"
        try:
            async with httpx.AsyncClient(timeout=settings.UHUNT_TIMEOUT_SECONDS) as client:
                res = await client.get(url)
                if res.status_code != 200:
                    return None
                data = res.json()
                if not data or not data.get("pid"):
                    return None

                existing_difficulty = (
                    self._dataset[problem_number].difficulty
                    if problem_number in self._dataset
                    else None
                )

                prob = ProblemData(
                    problem_number=problem_number,
                    title=data.get("title", f"UVa {problem_number}"),
                    difficulty=existing_difficulty,  # Never guess difficulty
                    uhunt_pid=data.get("pid"),
                    source="UVa Online Judge",
                    time_limit=data.get("rtl"),
                )
                self._dataset[problem_number] = prob
                return prob
        except Exception as e:
            logger.warning(f"Could not refresh metadata for problem #{problem_number}: {e}")
            if problem_number in self._dataset:
                return self._dataset[problem_number]
            return None
