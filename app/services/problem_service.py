import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.user import User
from app.repositories.problem_repo import ProblemRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.providers.problem_provider import BaseProblemProvider, CpeProblemProvider, ProblemData
from app.providers.uva_provider import UvaProvider

logger = logging.getLogger(__name__)


class UserNotLinkedException(Exception):
    """Raised when user attempts to start a problem without a linked UVa account."""
    pass


class ProblemNotFoundException(Exception):
    """Raised when the specified problem does not exist."""
    pass


class ProblemService:
    def __init__(
        self,
        problem_provider: Optional[BaseProblemProvider] = None,
        uva_provider: Optional[UvaProvider] = None,
    ) -> None:
        self.problem_provider = problem_provider or CpeProblemProvider()
        self.uva_provider = uva_provider or UvaProvider()

    async def get_problem(
        self,
        session: AsyncSession,
        problem_number: int
    ) -> Optional[Problem]:
        # Check database first
        problem = await ProblemRepository.get_by_number(session, problem_number)
        if problem:
            return problem

        # Fallback to provider
        data = await self.problem_provider.get_problem(problem_number)
        if not data:
            return None

        # Upsert into database
        problem = await ProblemRepository.upsert_from_data(session, data)
        return problem

    async def get_random_problem(
        self,
        session: AsyncSession,
        difficulty: Optional[str] = None
    ) -> Optional[Problem]:
        data = await self.problem_provider.get_random_problem(difficulty=difficulty)
        if not data:
            return None
        return await ProblemRepository.upsert_from_data(session, data)

    async def start_problem_session(
        self,
        session: AsyncSession,
        discord_user_id: int,
        problem_number: int,
        thread_id: Optional[int] = None,
        discord_username: Optional[str] = None,
    ) -> Tuple[ActiveProblemSession, bool]:
        """Start or retrieve an active problem session for the user.

        Returns:
            Tuple of (ActiveProblemSession, is_new_session: bool)
        """
        user = await UserRepository.get_or_create(session, discord_user_id, discord_username)
        if not user.uva_username or not user.uva_user_id:
            raise UserNotLinkedException("尚未綁定 UVa Account，請先使用 `/link <uva_username>`。")

        problem = await self.get_problem(session, problem_number)
        if not problem:
            raise ProblemNotFoundException(f"找不到題目 UVa {problem_number}。")

        # Check if an active session already exists for this user and problem
        existing = await SessionRepository.get_active_session(session, user.id, problem.id)
        if existing:
            logger.info(
                f"User {discord_user_id} already has active session for UVa {problem_number} (session_id={existing.id})"
            )
            return existing, False

        # Get initial last_submission_id from uHunt to avoid re-notifying past submissions
        last_sub_id = 0
        try:
            from app.providers.submission_provider import SubmissionProvider
            sub_provider = SubmissionProvider()
            last_sub_id = await sub_provider.get_latest_submission_id(user.uva_user_id)
        except Exception as e:
            logger.warning(f"Could not get initial last_submission_id for UID {user.uva_user_id}: {e}")

        new_session = await SessionRepository.create_session(
            session=session,
            user_id=user.id,
            problem_id=problem.id,
            thread_id=thread_id,
            last_submission_id=last_sub_id,
        )
        logger.info(
            f"User {discord_user_id} started UVa {problem_number} (session_id={new_session.id}, thread_id={thread_id}, initial last_sub_id={last_sub_id})"
        )
        return new_session, True

    async def get_active_session_by_user(
        self,
        session: AsyncSession,
        discord_user_id: int
    ) -> Optional[ActiveProblemSession]:
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user:
            return None
        return await SessionRepository.get_latest_active_by_user(session, user.id)

    async def close_problem_session(
        self,
        session: AsyncSession,
        discord_user_id: int
    ) -> Optional[ActiveProblemSession]:
        """Close the currently active problem session for the user."""
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user:
            return None
        return await SessionRepository.close_active_session_by_user(session, user.id)
