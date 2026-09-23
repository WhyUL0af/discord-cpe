from datetime import datetime
from typing import List, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.solved import UserSolvedProblem
from app.models.submission import Submission
from app.models.user import User


class RankingRepository:
    @staticmethod
    async def get_all_time_ranking(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Tuple[User, int]]:
        """Get all-time top users ranked by distinct solved problems."""
        stmt = (
            select(User, func.count(UserSolvedProblem.problem_id.distinct()).label("solved_count"))
            .join(UserSolvedProblem, User.id == UserSolvedProblem.user_id)
            .group_by(User.id)
            .order_by(func.count(UserSolvedProblem.problem_id.distinct()).desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def get_weekly_ranking(
        session: AsyncSession,
        start_of_week: datetime,
        limit: int = 10
    ) -> List[Tuple[User, int]]:
        """Get weekly top users ranked by distinct solved problems first accepted this week."""
        stmt = (
            select(User, func.count(UserSolvedProblem.problem_id.distinct()).label("solved_count"))
            .join(UserSolvedProblem, User.id == UserSolvedProblem.user_id)
            .where(UserSolvedProblem.first_accepted_at >= start_of_week)
            .group_by(User.id)
            .order_by(func.count(UserSolvedProblem.problem_id.distinct()).desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @staticmethod
    async def get_weekly_submission_stats(
        session: AsyncSession,
        start_of_week: datetime
    ) -> Tuple[int, int]:
        """Return (total_submissions, accepted_submissions) this week."""
        total_stmt = (
            select(func.count(Submission.id))
            .where(Submission.submitted_at >= start_of_week)
        )
        total_res = await session.execute(total_stmt)
        total = total_res.scalar_one() or 0

        ac_stmt = (
            select(func.count(Submission.id))
            .where(
                Submission.submitted_at >= start_of_week,
                Submission.verdict == "Accepted",
            )
        )
        ac_res = await session.execute(ac_stmt)
        accepted = ac_res.scalar_one() or 0

        return total, accepted
