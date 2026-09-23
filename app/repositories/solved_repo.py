from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.solved import UserSolvedProblem


class SolvedRepository:
    @staticmethod
    async def get_by_user_and_problem(
        session: AsyncSession,
        user_id: int,
        problem_id: int
    ) -> Optional[UserSolvedProblem]:
        stmt = select(UserSolvedProblem).where(
            UserSolvedProblem.user_id == user_id,
            UserSolvedProblem.problem_id == problem_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def record_solved(
        session: AsyncSession,
        user_id: int,
        problem_id: int,
        accepted_at: Optional[datetime] = None
    ) -> UserSolvedProblem:
        existing = await SolvedRepository.get_by_user_and_problem(session, user_id, problem_id)
        if existing:
            return existing

        solved = UserSolvedProblem(
            user_id=user_id,
            problem_id=problem_id,
            first_accepted_at=accepted_at or datetime.now(timezone.utc),
        )
        session.add(solved)
        await session.flush()
        return solved

    @staticmethod
    async def get_user_solved_problems(
        session: AsyncSession,
        user_id: int
    ) -> List[UserSolvedProblem]:
        stmt = (
            select(UserSolvedProblem)
            .where(UserSolvedProblem.user_id == user_id)
            .options(selectinload(UserSolvedProblem.problem))
            .order_by(UserSolvedProblem.first_accepted_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
