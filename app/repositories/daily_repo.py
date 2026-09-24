from datetime import date, datetime, time, timezone
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.daily import DailyProblem
from app.models.problem import Problem
from app.models.solved import UserSolvedProblem


class DailyRepository:
    @staticmethod
    async def get_by_guild_and_date(
        session: AsyncSession,
        guild_id: int,
        target_date: date
    ) -> Optional[DailyProblem]:
        """Fetch the daily problem for a specific guild and date with eager-loaded problem."""
        stmt = (
            select(DailyProblem)
            .where(
                DailyProblem.guild_id == guild_id,
                DailyProblem.date == target_date,
            )
            .options(selectinload(DailyProblem.problem))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_any_by_date(
        session: AsyncSession,
        target_date: date
    ) -> Optional[DailyProblem]:
        """Check if any guild has already generated a daily problem for this date."""
        stmt = (
            select(DailyProblem)
            .where(DailyProblem.date == target_date)
            .options(selectinload(DailyProblem.problem))
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_message_id(
        session: AsyncSession,
        message_id: int
    ) -> Optional[DailyProblem]:
        """Fetch the daily problem associated with a discord message ID with eager-loaded problem."""
        stmt = (
            select(DailyProblem)
            .where(DailyProblem.discord_message_id == message_id)
            .options(selectinload(DailyProblem.problem))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_recent_problem_ids(
        session: AsyncSession,
        days: int,
        guild_id: Optional[int] = None
    ) -> List[int]:
        """Fetch problem IDs selected in the last `days` days."""
        from datetime import timedelta
        cutoff = date.today() - timedelta(days=days)
        stmt = select(DailyProblem.problem_id).where(DailyProblem.date >= cutoff)
        if guild_id is not None:
            stmt = stmt.where(DailyProblem.guild_id == guild_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count_total_dailies_for_guild(session: AsyncSession, guild_id: int) -> int:
        stmt = select(func.count(DailyProblem.id)).where(DailyProblem.guild_id == guild_id)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def create_daily(
        session: AsyncSession,
        guild_id: int,
        target_date: date,
        problem_id: int,
        message_id: Optional[int] = None,
        problem_obj: Optional[Problem] = None,
    ) -> DailyProblem:
        daily = DailyProblem(
            guild_id=guild_id,
            date=target_date,
            problem_id=problem_id,
            discord_message_id=message_id,
        )
        if problem_obj is not None:
            daily.problem = problem_obj
        session.add(daily)
        await session.flush()
        return daily

    @staticmethod
    async def count_solved_on_date(
        session: AsyncSession,
        problem_id: int,
        target_date: date
    ) -> int:
        """Count how many distinct users solved problem_id on target_date."""
        start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
        stmt = (
            select(func.count(UserSolvedProblem.id))
            .where(
                UserSolvedProblem.problem_id == problem_id,
                UserSolvedProblem.first_accepted_at >= start_dt,
                UserSolvedProblem.first_accepted_at <= end_dt,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one() or 0
