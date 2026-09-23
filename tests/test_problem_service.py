import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.problem_service import (
    ProblemService,
    UserNotLinkedException,
    ProblemNotFoundException,
)
from app.providers.problem_provider import CpeProblemProvider, ProblemData
from app.repositories.user_repo import UserRepository


@pytest.mark.asyncio
async def test_get_problem(async_db_session):
    service = ProblemService()
    prob = await service.get_problem(async_db_session, 100)
    assert prob is not None
    assert prob.problem_number == 100
    assert prob.title == "The 3n + 1 problem"
    assert prob.difficulty == "⭐"


@pytest.mark.asyncio
async def test_start_problem_session_unlinked(async_db_session):
    service = ProblemService()
    with pytest.raises(UserNotLinkedException):
        await service.start_problem_session(
            session=async_db_session,
            discord_user_id=111222333,
            problem_number=100,
            thread_id=999,
        )


@pytest.mark.asyncio
async def test_start_problem_session_success_and_idempotent(async_db_session):
    # First link the user
    await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=111222333,
        uva_username="felix_halim",
        uva_user_id=339,
    )

    service = ProblemService()

    # First start -> creates new session
    session1, is_new1 = await service.start_problem_session(
        session=async_db_session,
        discord_user_id=111222333,
        problem_number=100,
        thread_id=888888,
    )
    assert is_new1 is True
    assert session1.thread_id == 888888
    assert session1.status == "active"

    # Second start on same problem -> returns existing session without creating a new one
    session2, is_new2 = await service.start_problem_session(
        session=async_db_session,
        discord_user_id=111222333,
        problem_number=100,
        thread_id=999999,
    )
    assert is_new2 is False
    assert session2.id == session1.id
    assert session2.thread_id == 888888
