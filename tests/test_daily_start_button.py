from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from app.bot.views.problem_view import (
    ActiveConflictView,
    DailyProblemView,
    ProblemSelectionView,
    start_problem_for_user,
)
from app.models.daily import DailyProblem
from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.providers.submission_provider import SubmissionProvider
from app.repositories.daily_repo import DailyRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.user_repo import UserRepository
from app.services.daily_service import DailyService
from app.services.practice_service import PracticeService
from app.services.problem_service import ProblemService


def make_mock_interaction(user_id=12345, username="test_coder", guild_id=999, message_id=888):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.User)
    interaction.user.id = user_id
    interaction.user.name = username
    interaction.guild_id = guild_id
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.message = MagicMock(spec=discord.Message)
    interaction.message.id = message_id

    # Interaction response mocks
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    return interaction


@pytest.fixture
async def setup_daily_env(async_db_session):
    """Sets up a Problem, a linked user, and an unlinked user."""
    # Problem UVa 11479
    prob = Problem(
        problem_number=11479,
        title="Is this the easiest problem?",
        difficulty="⭐",
        external_url="https://onlinejudge.org/external/114/11479.pdf",
    )
    async_db_session.add(prob)

    # Linked user
    linked_user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=1001,
        uva_username="cpe_hero",
        uva_user_id=50001,
    )

    # Unlinked user
    unlinked_user = await UserRepository.get_or_create(
        session=async_db_session,
        discord_user_id=1002,
        discord_username="noob_coder",
    )

    # Daily problem for guild 999
    daily = await DailyRepository.create_daily(
        session=async_db_session,
        guild_id=999,
        target_date=date.today(),
        problem_id=prob.id,
        message_id=888,
        problem_obj=prob,
    )
    await async_db_session.flush()

    return {
        "problem": prob,
        "linked_user": linked_user,
        "unlinked_user": unlinked_user,
        "daily": daily,
    }


# ==============================================================================
# 1 & 2. Daily Problem「開始作答」Button 可以正常執行，不再出現 Button object is not callable
# ==============================================================================
@pytest.mark.asyncio
async def test_01_and_02_daily_start_button_executes_without_callable_error(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)

    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=999)):
        mock_db.return_value.__aenter__.return_value = async_db_session

        # Directly invoke start_button callback
        await view.start_button.callback(interaction)

    # Verify no TypeError was thrown and followup was called
    assert interaction.followup.send.called
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True
    embed = kwargs.get("embed")
    assert embed is not None
    assert "已開始作答" in embed.title


# ==============================================================================
# 3. 未 Link UVa -> ephemeral error
# ==============================================================================
@pytest.mark.asyncio
async def test_03_unlinked_user_gets_ephemeral_warning_and_no_session(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)

    interaction = make_mock_interaction(user_id=1002)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

    # Verify ephemeral response
    assert interaction.followup.send.called
    args, kwargs = interaction.followup.send.call_args
    content = args[0] if args else kwargs.get("content", "")
    assert "尚未綁定 UVa 帳號" in content
    assert kwargs.get("ephemeral") is True

    # Verify no active session created
    active = await SessionRepository.get_latest_active_by_user(session=async_db_session, user_id=setup_daily_env["unlinked_user"].id)
    assert active is None


# ==============================================================================
# 4. 已 Link UVa -> 建立 Active Session
# ==============================================================================
@pytest.mark.asyncio
async def test_04_linked_user_creates_active_session(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)

    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=123456)):
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

    active = await SessionRepository.get_latest_active_by_user(session=async_db_session, user_id=setup_daily_env["linked_user"].id)
    assert active is not None
    assert active.status == "active"
    assert active.problem_id == prob.id
    assert active.last_submission_id == 123456
    assert active.thread_id is None


# ==============================================================================
# 5. Daily Problem 啟動的是正確 Daily Problem，不重新 random
# ==============================================================================
@pytest.mark.asyncio
async def test_05_daily_problem_starts_exact_problem_not_rerolled(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)

    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(ProblemService, "get_random_problem") as mock_random, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=100)):
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

        # Ensure get_random_problem is NEVER invoked
        assert not mock_random.called

    active = await SessionRepository.get_latest_active_by_user(session=async_db_session, user_id=setup_daily_env["linked_user"].id)
    assert active.problem.problem_number == 11479


# ==============================================================================
# 6. 同一 User + 同一題不 duplicate session
# ==============================================================================
@pytest.mark.asyncio
async def test_06_duplicate_start_does_not_create_duplicate_session(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)

    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=100)):
        mock_db.return_value.__aenter__.return_value = async_db_session

        # 1st click
        await view.start_button.callback(interaction)
        # 2nd click
        await view.start_button.callback(interaction)

    # Check session count for user
    active_sessions = await SessionRepository.get_all_active_sessions(async_db_session)
    user_sessions = [s for s in active_sessions if s.user_id == setup_daily_env["linked_user"].id]
    assert len(user_sessions) == 1

    # 2nd response notifies user they are already solving this problem
    kwargs = interaction.followup.send.call_args.kwargs
    embed = kwargs.get("embed")
    assert "你目前正在作答此題目" in embed.title


# ==============================================================================
# 7. 已有其他 Active Problem 不偷偷覆蓋
# ==============================================================================
@pytest.mark.asyncio
async def test_07_existing_different_active_session_not_overwritten(setup_daily_env, async_db_session):
    other_prob = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(other_prob)
    await async_db_session.flush()

    # User 1001 is already solving UVa 100
    await SessionRepository.create_session(
        session=async_db_session,
        user_id=setup_daily_env["linked_user"].id,
        problem_id=other_prob.id,
    )
    await async_db_session.flush()

    # User clicks start on Daily Problem (UVa 11479)
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)
    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

    # Active session MUST still be UVa 100, NOT UVa 11479
    current_active = await SessionRepository.get_latest_active_by_user(async_db_session, setup_daily_env["linked_user"].id)
    assert current_active.problem_id == other_prob.id

    # Conflict response rendered with ActiveConflictView
    kwargs = interaction.followup.send.call_args.kwargs
    embed = kwargs.get("embed")
    conflict_view = kwargs.get("view")
    assert "你目前正在作答其他題目" in embed.title
    assert isinstance(conflict_view, ActiveConflictView)


# ==============================================================================
# 8, 9, 10. Start response 是 ephemeral, 不建立 Channel, 不建立 Thread
# ==============================================================================
@pytest.mark.asyncio
async def test_08_09_10_start_response_ephemeral_no_channel_no_thread(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]
    view = DailyProblemView(prob)
    interaction = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=1)):
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

    # 8. Ephemeral response
    assert interaction.followup.send.call_args.kwargs.get("ephemeral") is True
    # 9. No Channel creation
    assert not interaction.guild.create_text_channel.called
    # 10. No Thread creation
    assert not interaction.channel.create_thread.called


# ==============================================================================
# 11. Bot restart 後 persistent DailyProblemView 仍可運作 (problem=None)
# ==============================================================================
@pytest.mark.asyncio
async def test_11_restart_persistent_daily_problem_view_works(setup_daily_env, async_db_session):
    # Persistent view instance registered without problem in client.py
    persistent_view = DailyProblemView(problem=None)
    assert persistent_view.problem is None
    assert persistent_view.timeout is None

    # Interaction arrives with message.id matching daily problem (888)
    interaction = make_mock_interaction(user_id=1001, message_id=888, guild_id=999)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=777)):
        mock_db.return_value.__aenter__.return_value = async_db_session

        # 1. Test start_button on persistent view
        await persistent_view.start_button.callback(interaction)

    # Verify session created for UVa 11479
    active = await SessionRepository.get_latest_active_by_user(async_db_session, setup_daily_env["linked_user"].id)
    assert active is not None
    assert active.problem.problem_number == 11479
    assert active.last_submission_id == 777

    # 2. Test stats_button on persistent view
    with patch("app.bot.views.problem_view.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await persistent_view.stats_button.callback(interaction)

    kwargs = interaction.followup.send.call_args.kwargs
    embed = kwargs.get("embed")
    assert "今日解題統計：UVa 11479" in embed.title


# ==============================================================================
# 12. Practice Center「開始作答」與 PracticeService 也使用相同 business logic
# ==============================================================================
@pytest.mark.asyncio
async def test_12_practice_center_and_practice_service_share_logic(setup_daily_env, async_db_session):
    prob = setup_daily_env["problem"]

    # 1. Practice Center ProblemSelectionView
    selection_view = ProblemSelectionView(prob)
    interaction_1 = make_mock_interaction(user_id=1001)

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=500)):
        mock_db.return_value.__aenter__.return_value = async_db_session
        await selection_view.start_button.callback(interaction_1)

    active = await SessionRepository.get_latest_active_by_user(async_db_session, setup_daily_env["linked_user"].id)
    assert active is not None
    assert active.problem_id == prob.id

    # 2. PracticeService.start_problem
    interaction_2 = make_mock_interaction(user_id=1001)
    with patch("app.bot.views.problem_view.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await PracticeService.start_problem(interaction=interaction_2, problem=prob)

    # Returns already solving
    kwargs = interaction_2.followup.send.call_args.kwargs
    embed = kwargs.get("embed")
    assert "你目前正在作答此題目" in embed.title
