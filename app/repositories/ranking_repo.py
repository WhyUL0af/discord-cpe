from datetime import datetime
from typing import List, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.submission import Submission
from app.models.user import User


def external_solved_query():
    """First external AC per user/problem; excludes website and mock scores."""
    return (select(Submission.user_id.label("user_id"), Submission.problem_id.label("problem_id"),
        func.min(Submission.submitted_at).label("first_accepted_at"))
        .where(Submission.source == "uhunt", Submission.external_submission_id.isnot(None),
               Submission.verdict == "Accepted")
        .group_by(Submission.user_id, Submission.problem_id).subquery())


class RankingRepository:
    @staticmethod
    async def get_all_time_ranking(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Tuple[User, int]]:
        """Get all-time top users ranked by distinct solved problems."""
        solved = external_solved_query()
        stmt = (
            select(User, func.count(solved.c.problem_id).label("solved_count"))
            .join(solved, User.id == solved.c.user_id)
            .group_by(User.id)
            .order_by(func.count(solved.c.problem_id).desc(), User.discord_user_id.asc())
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
        solved = external_solved_query()
        stmt = (
            select(User, func.count(solved.c.problem_id).label("solved_count"))
            .join(solved, User.id == solved.c.user_id)
            .where(solved.c.first_accepted_at >= start_of_week)
            .group_by(User.id)
            .order_by(func.count(solved.c.problem_id).desc(), User.discord_user_id.asc())
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
            .where(Submission.submitted_at >= start_of_week,
                   Submission.source == "uhunt", Submission.external_submission_id.isnot(None))
        )
        total_res = await session.execute(total_stmt)
        total = total_res.scalar_one() or 0

        ac_stmt = (
            select(func.count(Submission.id))
            .where(
                Submission.submitted_at >= start_of_week,
                Submission.verdict == "Accepted",
                Submission.source == "uhunt",
                Submission.external_submission_id.isnot(None),
            )
        )
        ac_res = await session.execute(ac_stmt)
        accepted = ac_res.scalar_one() or 0

        return total, accepted
