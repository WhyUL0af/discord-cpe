import logging
from datetime import datetime, timezone
from typing import List, NamedTuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.user import User
from app.repositories.session_repo import SessionRepository
from app.repositories.solved_repo import SolvedRepository
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.user_repo import UserRepository
from app.providers.submission_provider import SubmissionData, SubmissionProvider

from app.models.submission import Submission

logger = logging.getLogger(__name__)


class SubmissionNotification(NamedTuple):
    session_id: int
    discord_user_id: int
    problem_number: int
    problem_title: str
    submission_id: int
    language: str
    verdict: str
    display_verdict: str
    runtime: Optional[int]
    attempts: int
    is_accepted: bool
    started_at: datetime
    solved_at: Optional[datetime] = None
    thread_id: Optional[int] = None


class SubmissionService:
    def __init__(self, provider: Optional[SubmissionProvider] = None) -> None:
        self.provider = provider or SubmissionProvider()

    async def check_session_submissions(
        self,
        session: AsyncSession,
        active_session: ActiveProblemSession,
    ) -> List[SubmissionNotification]:
        """Check for new submissions in uHunt for the given active session.

        Records submissions and updates session status if solved.
        Returns a list of notification events to dispatch to Discord.
        """
        user: User = active_session.user
        problem: Problem = active_session.problem

        if not user.uva_user_id or not problem.uhunt_pid:
            return []

        # Fetch new submissions since last tracked submission ID
        new_subs = await self.provider.get_user_submissions_since(
            uva_user_id=user.uva_user_id,
            min_sub_id=active_session.last_submission_id,
        )

        notifications: List[SubmissionNotification] = []

        for sub in new_subs:
            # Check if this submission is for the current problem
            if sub.uhunt_pid != problem.uhunt_pid:
                # Update last_submission_id to avoid querying it repeatedly
                if sub.submission_id > active_session.last_submission_id:
                    active_session.last_submission_id = sub.submission_id
                continue

            # Record submission in DB
            submitted_at = (
                datetime.fromtimestamp(sub.submission_time, tz=timezone.utc)
                if sub.submission_time
                else datetime.now(timezone.utc)
            )
            await SubmissionRepository.record_submission(
                session=session,
                user_id=user.id,
                problem_id=problem.id,
                external_submission_id=sub.submission_id,
                verdict=sub.verdict,
                runtime=sub.runtime,
                submitted_at=submitted_at,
            )

            # Update session's last_submission_id
            if sub.submission_id > active_session.last_submission_id:
                active_session.last_submission_id = sub.submission_id

            # Count attempts on this problem
            attempts = await SubmissionRepository.count_attempts(session, user.id, problem.id)

            is_accepted = sub.is_accepted

            if is_accepted:
                active_session.status = "solved"
                active_session.solved_at = submitted_at
                await SolvedRepository.record_solved(
                    session=session,
                    user_id=user.id,
                    problem_id=problem.id,
                    accepted_at=submitted_at,
                )
                logger.info(
                    f"User {user.discord_user_id} solved UVa {problem.problem_number} in {attempts} attempt(s)!"
                )

            notifications.append(
                SubmissionNotification(
                    session_id=active_session.id,
                    discord_user_id=user.discord_user_id,
                    problem_number=problem.problem_number,
                    problem_title=problem.title,
                    submission_id=sub.submission_id,
                    language=sub.language,
                    verdict=sub.verdict,
                    display_verdict=sub.display_verdict,
                    runtime=sub.runtime,
                    attempts=attempts,
                    is_accepted=is_accepted,
                    started_at=active_session.started_at,
                    solved_at=active_session.solved_at if is_accepted else None,
                    thread_id=active_session.thread_id,
                )
            )

            # If accepted, no need to check further submissions for this session
            if is_accepted:
                break

        await session.flush()
        return notifications

    async def get_user_solved(
        self,
        session: AsyncSession,
        discord_user_id: int
    ) -> List[tuple[int, str]]:
        """Returns list of (problem_number, title) solved by the user."""
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user:
            return []

        solved_list = await SolvedRepository.get_user_solved_problems(session, user.id)
        return [(s.problem.problem_number, s.problem.title) for s in solved_list]

    async def get_recent_submissions_for_problem(
        self,
        session: AsyncSession,
        user_id: int,
        problem_id: int,
        limit: int = 5,
    ) -> List[Submission]:
        """Fetch recent submissions for a specific user and problem."""
        return await SubmissionRepository.get_recent_submissions_for_problem(
            session=session,
            user_id=user_id,
            problem_id=problem_id,
            limit=limit,
        )
