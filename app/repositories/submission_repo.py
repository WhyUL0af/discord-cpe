from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission


class SubmissionRepository:
    @staticmethod
    async def get_by_external_id(
        session: AsyncSession,
        external_submission_id: int
    ) -> Optional[Submission]:
        stmt = select(Submission).where(Submission.external_submission_id == external_submission_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def record_submission(
        session: AsyncSession,
        user_id: int,
        problem_id: int,
        external_submission_id: int,
        verdict: str,
        runtime: Optional[int] = None,
        submitted_at: Optional[datetime] = None,
    ) -> Submission:
        existing = await SubmissionRepository.get_by_external_id(session, external_submission_id)
        if existing:
            return existing

        sub = Submission(
            user_id=user_id,
            problem_id=problem_id,
            external_submission_id=external_submission_id,
            verdict=verdict,
            runtime=runtime,
            submitted_at=submitted_at or datetime.now(timezone.utc),
        )
        session.add(sub)
        await session.flush()
        return sub

    @staticmethod
    async def count_attempts(
        session: AsyncSession,
        user_id: int,
        problem_id: int
    ) -> int:
        stmt = (
            select(func.count(Submission.id))
            .where(
                Submission.user_id == user_id,
                Submission.problem_id == problem_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    @staticmethod
    async def get_recent_submissions_for_problem(
        session: AsyncSession,
        user_id: int,
        problem_id: int,
        limit: int = 5,
    ) -> list[Submission]:
        stmt = (
            select(Submission)
            .where(
                Submission.user_id == user_id,
                Submission.problem_id == problem_id,
            )
            .order_by(Submission.submitted_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
