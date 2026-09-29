"""Read-only dashboard queries against the Bot's existing tables."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Problem, Submission, UserSolvedProblem


class DashboardRepository:
    @staticmethod
    async def progress(session: AsyncSession, user_id: int) -> tuple[int, int]:
        solved = await session.scalar(select(func.count(UserSolvedProblem.id)).where(
            UserSolvedProblem.user_id == user_id)) or 0
        total = await session.scalar(select(func.count(Problem.id))) or 0
        return solved, total

    @staticmethod
    async def recent_submissions(session: AsyncSession, user_id: int):
        return list((await session.scalars(select(Submission).where(
            Submission.user_id == user_id).options(selectinload(Submission.problem))
            .order_by(Submission.submitted_at.desc(), Submission.id.desc()).limit(5))).all())

    @staticmethod
    async def continue_problem(session: AsyncSession, user_id: int):
        solved = select(UserSolvedProblem.problem_id).where(UserSolvedProblem.user_id == user_id)
        return await session.scalar(select(Problem).join(Submission).where(
            Submission.user_id == user_id, Problem.id.not_in(solved))
            .order_by(Submission.submitted_at.desc(), Submission.id.desc()).limit(1))
