from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session import ActiveProblemSession


class SessionRepository:
    @staticmethod
    async def get_active_session(
        session: AsyncSession,
        user_id: int,
        problem_id: int
    ) -> Optional[ActiveProblemSession]:
        stmt = (
            select(ActiveProblemSession)
            .where(
                ActiveProblemSession.user_id == user_id,
                ActiveProblemSession.problem_id == problem_id,
                ActiveProblemSession.status == "active",
            )
            .options(
                selectinload(ActiveProblemSession.user),
                selectinload(ActiveProblemSession.problem),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_by_thread_id(
        session: AsyncSession,
        thread_id: int
    ) -> Optional[ActiveProblemSession]:
        stmt = (
            select(ActiveProblemSession)
            .where(ActiveProblemSession.thread_id == thread_id)
            .options(
                selectinload(ActiveProblemSession.user),
                selectinload(ActiveProblemSession.problem),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_active_by_user(
        session: AsyncSession,
        user_id: int
    ) -> Optional[ActiveProblemSession]:
        stmt = (
            select(ActiveProblemSession)
            .where(
                ActiveProblemSession.user_id == user_id,
                ActiveProblemSession.status == "active",
            )
            .order_by(ActiveProblemSession.started_at.desc())
            .options(
                selectinload(ActiveProblemSession.user),
                selectinload(ActiveProblemSession.problem),
            )
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_all_active_sessions(
        session: AsyncSession
    ) -> List[ActiveProblemSession]:
        """Fetch all sessions that are currently 'active' for the submission tracking loop."""
        stmt = (
            select(ActiveProblemSession)
            .where(ActiveProblemSession.status == "active")
            .options(
                selectinload(ActiveProblemSession.user),
                selectinload(ActiveProblemSession.problem),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create_session(
        session: AsyncSession,
        user_id: int,
        problem_id: int,
        thread_id: Optional[int] = None,
        last_submission_id: int = 0
    ) -> ActiveProblemSession:
        prob_session = ActiveProblemSession(
            user_id=user_id,
            problem_id=problem_id,
            thread_id=thread_id,
            last_submission_id=last_submission_id,
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        session.add(prob_session)
        await session.flush()
        return prob_session

    @staticmethod
    async def close_session(
        session: AsyncSession,
        session_id: int,
    ) -> Optional[ActiveProblemSession]:
        return await SessionRepository.update_status(session, session_id, status="closed")

    @staticmethod
    async def close_active_session_by_user(
        session: AsyncSession,
        user_id: int,
    ) -> Optional[ActiveProblemSession]:
        active = await SessionRepository.get_latest_active_by_user(session, user_id)
        if active:
            active.status = "closed"
            await session.flush()
            return active
        return None

    @staticmethod
    async def update_status(
        session: AsyncSession,
        session_id: int,
        status: str,
        solved_at: Optional[datetime] = None
    ) -> Optional[ActiveProblemSession]:
        stmt = select(ActiveProblemSession).where(ActiveProblemSession.id == session_id)
        result = await session.execute(stmt)
        prob_session = result.scalar_one_or_none()
        if prob_session:
            prob_session.status = status
            if solved_at:
                prob_session.solved_at = solved_at
            await session.flush()
        return prob_session

    @staticmethod
    async def update_last_submission_id(
        session: AsyncSession,
        session_id: int,
        last_submission_id: int
    ) -> None:
        stmt = select(ActiveProblemSession).where(ActiveProblemSession.id == session_id)
        result = await session.execute(stmt)
        prob_session = result.scalar_one_or_none()
        if prob_session:
            prob_session.last_submission_id = last_submission_id
            await session.flush()
