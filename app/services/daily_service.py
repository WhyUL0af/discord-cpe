import logging
import random
from datetime import date
from typing import Optional, Tuple
from sqlalchemy.exc import IntegrityError
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
        guild_id: int,
        target_date: Optional[date] = None,
    ) -> Tuple[DailyProblem, int]:
        """Get or pick the daily problem for a specific guild and date.

        Guarantees:
        - Each guild has at most one DailyProblem per date.
        - Idempotent and restart-safe: once selected, subsequent calls or restarts retrieve the existing record.
        - Problem relationship is eager-loaded (never triggers lazy IO / MissingGreenlet).
        - Concurrency-safe against race conditions via DB UNIQUE constraint and nested savepoints.

        Returns:
            Tuple of (DailyProblem, daily_sequence_number)
        """
        today = target_date or date.today()

        # 1. Check if daily problem for (guild_id, today) already exists
        existing = await DailyRepository.get_by_guild_and_date(session, guild_id, today)
        total_count = await DailyRepository.count_total_dailies_for_guild(session, guild_id)

        if existing:
            return existing, max(1, total_count)

        # 2. Check if another guild already selected a problem for today (synchronize daily problem across guilds)
        selected_problem: Optional[Problem] = None
        any_daily_today = await DailyRepository.get_any_by_date(session, today)
        if any_daily_today and any_daily_today.problem:
            selected_problem = any_daily_today.problem

        # If no problem has been chosen anywhere for today, select from eligible pool
        if not selected_problem:
            cooldown_days = settings.DAILY_REPEAT_COOLDOWN_DAYS
            recent_ids = await DailyRepository.get_recent_problem_ids(session, cooldown_days)

            # Ensure dataset problems exist in database
            all_dataset_problems = await self.provider.get_problems()
            for p_data in all_dataset_problems:
                await ProblemRepository.upsert_from_data(session, p_data)

            all_problems = await ProblemRepository.get_all(session)
            eligible = [p for p in all_problems if p.id not in recent_ids]

            if not eligible:
                eligible = all_problems

            if not eligible:
                raise RuntimeError("No problems available in database for Daily Problem selection.")

            selected_problem = random.choice(eligible)
            logger.info(
                f"Selected Daily Problem for {today}: UVa {selected_problem.problem_number} ({selected_problem.title})"
            )

        # 3. Insert new DailyProblem handling concurrent race conditions
        try:
            async with session.begin_nested():
                daily = await DailyRepository.create_daily(
                    session=session,
                    guild_id=guild_id,
                    target_date=today,
                    problem_id=selected_problem.id,
                    problem_obj=selected_problem,
                )
                await session.flush()
        except IntegrityError:
            # Another concurrent task created the record simultaneously
            existing = await DailyRepository.get_by_guild_and_date(session, guild_id, today)
            if existing:
                total_count = await DailyRepository.count_total_dailies_for_guild(session, guild_id)
                return existing, max(1, total_count)
            raise

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
