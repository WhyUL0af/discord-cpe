import logging
import random
from datetime import date, timezone
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.daily import DailyProblem
from app.models.problem import Problem
from app.repositories.daily_repo import DailyRepository
from app.repositories.problem_repo import ProblemRepository
from app.providers.problem_provider import BaseProblemProvider, CpeProblemProvider

logger = logging.getLogger(__name__)


class DailyService:
    def __init__(self, provider: Optional[BaseProblemProvider] = None) -> None:
        self.provider = provider or CpeProblemProvider()

    async def get_or_create_daily_problem(
        self,
        session: AsyncSession,
        target_date: Optional[date] = None,
    ) -> Tuple[DailyProblem, int]:
        """Get or pick the daily problem for the given date.

        Guarantees that once chosen, restarting the bot will not re-pick another problem.
        Returns:
            Tuple of (DailyProblem, daily_sequence_number)
        """
        today = target_date or date.today()

        # 1. Check if daily problem for today is already recorded
        existing = await DailyRepository.get_by_date(session, today)
        total_count = await DailyRepository.count_total_dailies(session)

        if existing:
            return existing, max(1, total_count)

        # 2. Pick a problem excluding recent cooldown days
        cooldown_days = settings.DAILY_REPEAT_COOLDOWN_DAYS
        recent_ids = await DailyRepository.get_recent_problem_ids(session, cooldown_days)

        # Ensure all dataset problems are in the database
        all_dataset_problems = await self.provider.get_problems()
        for p_data in all_dataset_problems:
            await ProblemRepository.upsert_from_data(session, p_data)

        all_problems = await ProblemRepository.get_all(session)
        eligible = [p for p in all_problems if p.id not in recent_ids]

        # If all problems were used recently, fall back to all available problems
        if not eligible:
            eligible = all_problems

        if not eligible:
            raise RuntimeError("No problems available in database for Daily Problem selection.")

        selected_problem = random.choice(eligible)
        daily = await DailyRepository.create_daily(
            session=session,
            target_date=today,
            problem_id=selected_problem.id,
        )
        logger.info(
            f"Selected Daily Problem for {today}: UVa {selected_problem.problem_number} ({selected_problem.title})"
        )

        daily_number = total_count + 1
        return daily, daily_number

    async def count_solved_today(
        self,
        session: AsyncSession,
        problem_id: int,
        target_date: Optional[date] = None,
    ) -> int:
        today = target_date or date.today()
        return await DailyRepository.count_solved_on_date(session, problem_id, today)
