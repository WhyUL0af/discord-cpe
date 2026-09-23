from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.submission import Submission
from app.models.user import User
from app.models.solved import UserSolvedProblem
from app.providers.submission_provider import SubmissionData, SubmissionProvider
from app.repositories.session_repo import SessionRepository
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.user_repo import UserRepository
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService, SubmissionNotification
from app.tasks.submission_tracker import SubmissionTracker
from app.bot.views.problem_view import (
    CurrentProblemView,
    PracticeCenterView,
    ProblemSelectionView,
    create_current_problem_embed,
    create_practice_center_embed,
    create_problem_embed,
)


@pytest.mark.asyncio
async def test_start_problem_session_without_thread(async_db_session):
    """Test starting a problem session creates an ActiveProblemSession with thread_id=None (no thread)."""
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=11111,
        uva_username="test_solver",
        uva_user_id=999,
    )
    problem = Problem(
        problem_number=10041,
        uhunt_pid=982,
        title="Vito's Family",
        difficulty="⭐",
    )
    async_db_session.add(problem)
    await async_db_session.flush()

    service = ProblemService()
    # Mock latest submission id from uHunt
    with patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=5000)):
        session_obj, is_new = await service.start_problem_session(
            session=async_db_session,
            discord_user_id=11111,
            problem_number=10041,
            thread_id=None,
        )

    assert is_new is True
    assert session_obj.thread_id is None
    assert session_obj.status == "active"
    assert session_obj.last_submission_id == 5000

    # Repeating start_problem_session for same user + problem returns existing session
    session_obj2, is_new2 = await service.start_problem_session(
        session=async_db_session,
        discord_user_id=11111,
        problem_number=10041,
        thread_id=None,
    )
    assert is_new2 is False
    assert session_obj2.id == session_obj.id


@pytest.mark.asyncio
async def test_close_problem_session(async_db_session):
    """Test closing an active problem session."""
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=22222,
        uva_username="test_solver_2",
        uva_user_id=1001,
    )
    problem = Problem(
        problem_number=100,
        uhunt_pid=36,
        title="3n+1",
        difficulty="⭐",
    )
    async_db_session.add(problem)
    await async_db_session.flush()

    service = ProblemService()
    with patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=0)):
        await service.start_problem_session(
            session=async_db_session,
            discord_user_id=22222,
            problem_number=100,
            thread_id=None,
        )

    # Active session should exist
    active = await service.get_active_session_by_user(async_db_session, 22222)
    assert active is not None
    assert active.status == "active"

    # Close the session
    closed = await service.close_problem_session(async_db_session, 22222)
    assert closed is not None
    assert closed.status == "closed"

    # Subsequent active query should be None
    active_after = await service.get_active_session_by_user(async_db_session, 22222)
    assert active_after is None


@pytest.mark.asyncio
async def test_recent_submissions_query(async_db_session):
    """Test querying recent submissions for /cpe current."""
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=33333,
        uva_username="test_solver_3",
        uva_user_id=1002,
    )
    problem = Problem(
        problem_number=10107,
        uhunt_pid=1048,
        title="What is the Median?",
        difficulty="⭐",
    )
    async_db_session.add(problem)
    await async_db_session.flush()

    # Record 3 submissions
    now = datetime.now(timezone.utc)
    for i in range(1, 4):
        await SubmissionRepository.record_submission(
            session=async_db_session,
            user_id=user.id,
            problem_id=problem.id,
            external_submission_id=8000 + i,
            verdict="Wrong Answer" if i < 3 else "Accepted",
            runtime=10 * i,
            submitted_at=now + timedelta(minutes=i),
        )

    recent = await SubmissionRepository.get_recent_submissions_for_problem(
        session=async_db_session,
        user_id=user.id,
        problem_id=problem.id,
        limit=5,
    )
    assert len(recent) == 3
    # Ordered descending: latest first
    assert recent[0].external_submission_id == 8003
    assert recent[0].verdict == "Accepted"
    assert recent[1].external_submission_id == 8002


@pytest.mark.asyncio
async def test_submission_tracker_dm_dispatch_success():
    """Test SubmissionTracker sending DM on AC and WA."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    mock_user = AsyncMock()
    bot.get_user.return_value = mock_user

    tracker = SubmissionTracker(bot)
    tracker.track_submissions.cancel()

    # 1. AC notification
    started_at = datetime.now(timezone.utc) - timedelta(minutes=24)
    solved_at = datetime.now(timezone.utc)
    notif_ac = SubmissionNotification(
        session_id=1,
        discord_user_id=44444,
        problem_number=10041,
        problem_title="Vito's Family",
        submission_id=1234567,
        language="C++11",
        verdict="Accepted",
        display_verdict="✅ Accepted",
        runtime=15,
        attempts=2,
        is_accepted=True,
        started_at=started_at,
        solved_at=solved_at,
    )

    await tracker._dispatch_notification(notif_ac)
    assert mock_user.send.called
    call_args = mock_user.send.call_args
    embed = call_args.kwargs.get("embed")
    assert embed is not None
    assert "Accepted (AC)" in embed.title
    # Check fields in embed
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Submission ID"] == "1234567"
    assert fields["語言"] == "C++11"
    assert "24 分鐘" in fields["作答歷時"]
    assert "2 次" in fields["嘗試次數"]

    # 2. WA notification
    mock_user.reset_mock()
    notif_wa = SubmissionNotification(
        session_id=1,
        discord_user_id=44444,
        problem_number=10041,
        problem_title="Vito's Family",
        submission_id=1234566,
        language="C++11",
        verdict="Wrong Answer",
        display_verdict="❌ Wrong Answer",
        runtime=15,
        attempts=1,
        is_accepted=False,
        started_at=started_at,
    )

    await tracker._dispatch_notification(notif_wa)
    assert mock_user.send.called
    embed_wa = mock_user.send.call_args.kwargs.get("embed")
    assert "Wrong Answer" in embed_wa.title


@pytest.mark.asyncio
async def test_submission_tracker_dm_failure_does_not_crash(async_db_session):
    """Test that when a user has closed DMs (discord.Forbidden), DM dispatch fails gracefully without error."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    mock_user = AsyncMock()
    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.reason = "Forbidden"
    mock_user.send.side_effect = discord.Forbidden(mock_response, "Cannot send messages to this user")
    bot.get_user.return_value = mock_user

    tracker = SubmissionTracker(bot)
    tracker.track_submissions.cancel()

    notif = SubmissionNotification(
        session_id=1,
        discord_user_id=55555,
        problem_number=100,
        problem_title="3n+1",
        submission_id=999999,
        language="C++",
        verdict="Accepted",
        display_verdict="✅ Accepted",
        runtime=10,
        attempts=1,
        is_accepted=True,
        started_at=datetime.now(timezone.utc),
        solved_at=datetime.now(timezone.utc),
    )

    # Must NOT raise exception despite Forbidden
    await tracker._dispatch_notification(notif)


@pytest.mark.asyncio
async def test_practice_center_view_components():
    """Verify PracticeCenterView has all 5 required buttons with correct custom_ids."""
    view = PracticeCenterView()
    assert view.timeout is None

    custom_ids = [item.custom_id for item in view.children if hasattr(item, "custom_id")]
    assert "cpe_practice_random" in custom_ids
    assert "cpe_practice_easy" in custom_ids
    assert "cpe_practice_search" in custom_ids
    assert "cpe_practice_current" in custom_ids
    assert "cpe_practice_solved" in custom_ids


@pytest.mark.asyncio
async def test_current_problem_view_components():
    """Verify CurrentProblemView has refresh and close buttons."""
    problem = Problem(problem_number=100, title="3n+1", external_url="https://onlinejudge.org/external/1/100.pdf")
    view = CurrentProblemView(problem)

    custom_ids = [item.custom_id for item in view.children if hasattr(item, "custom_id")]
    assert "cpe_current_refresh" in custom_ids
    assert "cpe_current_close" in custom_ids


def test_embed_generators():
    """Verify embed structures for practice center and current problem."""
    center_embed = create_practice_center_embed()
    assert "CPE 刷題中心" in center_embed.title
    assert "隨機題目" in center_embed.description
    assert "一星題目" in center_embed.description

    prob = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    p_embed = create_problem_embed(prob)
    assert "UVa 100" in p_embed.title

    session_obj = ActiveProblemSession(
        user_id=1,
        problem_id=1,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    cur_embed = create_current_problem_embed(prob, session_obj, attempts=3, recent_submissions=[])
    assert "目前作答題目" in cur_embed.title
    assert "15 分鐘" in [f.value for f in cur_embed.fields if f.name == "作答歷時"][0]
