import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.user import User
from app.models.solved import UserSolvedProblem
from app.providers.submission_provider import SubmissionData, SubmissionProvider
from app.repositories.problem_repo import ProblemRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.services.submission_service import SubmissionService


@pytest.mark.asyncio
async def test_submission_tracking_wa_then_ac(async_db_session):
    # Setup user and problem
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=12345,
        uva_username="felix_halim",
        uva_user_id=339,
    )
    problem = Problem(
        problem_number=100,
        uhunt_pid=36,
        title="The 3n + 1 problem",
        difficulty="⭐",
    )
    async_db_session.add(problem)
    await async_db_session.flush()

    active_session = await SessionRepository.create_session(
        session=async_db_session,
        user_id=user.id,
        problem_id=problem.id,
        thread_id=999001,
        last_submission_id=1000,
    )
    # Re-fetch session with loaded user and problem relationships
    loaded_session = await SessionRepository.get_active_session(
        async_db_session, user.id, problem.id
    )

    # 1. User submits WA
    mock_provider = MagicMock(spec=SubmissionProvider)
    mock_provider.get_user_submissions_since = AsyncMock(return_value=[
        SubmissionData(
            submission_id=1005,
            uhunt_pid=36,
            verdict_id=70,  # Wrong Answer
            runtime=15,
            submission_time=1700000000,
            language_id=3,
        )
    ])

    service = SubmissionService(provider=mock_provider)
    notifs = await service.check_session_submissions(async_db_session, loaded_session)

    assert len(notifs) == 1
    assert notifs[0].verdict == "Wrong Answer"
    assert notifs[0].is_accepted is False
    assert notifs[0].attempts == 1
    assert loaded_session.status == "active"
    assert loaded_session.last_submission_id == 1005

    # 2. User submits AC
    mock_provider.get_user_submissions_since = AsyncMock(return_value=[
        SubmissionData(
            submission_id=1010,
            uhunt_pid=36,
            verdict_id=90,  # Accepted
            runtime=10,
            submission_time=1700000100,
            language_id=3,
        )
    ])

    notifs_ac = await service.check_session_submissions(async_db_session, loaded_session)
    assert len(notifs_ac) == 1
    assert notifs_ac[0].verdict == "Accepted"
    assert notifs_ac[0].is_accepted is True
    assert notifs_ac[0].attempts == 2
    assert loaded_session.status == "solved"
    assert loaded_session.last_submission_id == 1010

    # Verify user_solved_problems entry exists
    solved_list = await service.get_user_solved(async_db_session, 12345)
    assert len(solved_list) == 1
    assert solved_list[0][0] == 100
