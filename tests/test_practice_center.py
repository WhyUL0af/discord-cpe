import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from app.models.guild import GuildSettings
from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.submission import Submission
from app.models.user import User
from app.models.solved import UserSolvedProblem
from app.providers.submission_provider import SubmissionData, SubmissionProvider
from app.repositories.guild_repo import GuildRepository
from app.repositories.problem_repo import ProblemRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.solved_repo import SolvedRepository
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.user_repo import UserRepository
from app.services.problem_service import (
    ActiveSessionConflictException,
    ProblemService,
)
from app.services.submission_service import SubmissionService, SubmissionNotification
from app.tasks.submission_tracker import SubmissionTracker
from app.bot.commands.setup_cog import deploy_or_sync_practice_center
from app.bot.commands.problem_cog import CpeGroup
from app.bot.views.problem_view import (
    ActiveConflictView,
    CurrentProblemView,
    PracticeCenterView,
    ProblemSearchModal,
    ProblemSelectionView,
    create_current_problem_embed,
    create_practice_center_embed,
    create_problem_embed,
)


# ==============================================================================
# 1. Random Problem response is ephemeral
# ==============================================================================
@pytest.mark.asyncio
async def test_01_random_problem_response_is_ephemeral(async_db_session):
    problem_service = ProblemService()
    submission_service = SubmissionService()
    cpe_group = CpeGroup(problem_service, submission_service)

    # Seed problem
    prob = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(prob)
    await async_db_session.flush()

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.commands.problem_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await cpe_group.random.callback(cpe_group, interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    assert interaction.followup.send.called
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True


# ==============================================================================
# 2. Easy Problem response is ephemeral
# ==============================================================================
@pytest.mark.asyncio
async def test_02_easy_problem_response_is_ephemeral(async_db_session):
    problem_service = ProblemService()
    submission_service = SubmissionService()
    cpe_group = CpeGroup(problem_service, submission_service)

    prob = Problem(problem_number=10041, title="Vito's Family", difficulty="⭐")
    async_db_session.add(prob)
    await async_db_session.flush()

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.commands.problem_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await cpe_group.easy.callback(cpe_group, interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    assert interaction.followup.send.called
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True


# ==============================================================================
# 3. Specified Problem response is ephemeral
# ==============================================================================
@pytest.mark.asyncio
async def test_03_specified_problem_response_is_ephemeral(async_db_session):
    problem_service = ProblemService()
    prob = Problem(problem_number=10107, title="Median", difficulty="⭐")
    async_db_session.add(prob)
    await async_db_session.flush()

    modal = ProblemSearchModal(problem_service)
    modal.problem_input._value = "10107"

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.views.problem_view.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await modal.on_submit(interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    assert interaction.followup.send.called
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True


# ==============================================================================
# 4. Current Problem response is ephemeral
# ==============================================================================
@pytest.mark.asyncio
async def test_04_current_problem_response_is_ephemeral(async_db_session):
    problem_service = ProblemService()
    submission_service = SubmissionService()
    cpe_group = CpeGroup(problem_service, submission_service)

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user.id = 99999
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.commands.problem_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await cpe_group.current.callback(cpe_group, interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True


# ==============================================================================
# 5. Solved response is ephemeral
# ==============================================================================
@pytest.mark.asyncio
async def test_05_solved_response_is_ephemeral(async_db_session):
    problem_service = ProblemService()
    submission_service = SubmissionService()
    cpe_group = CpeGroup(problem_service, submission_service)

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user.id = 99999
    interaction.user.display_name = "TestUser"
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.commands.problem_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        await cpe_group.solved.callback(cpe_group, interaction, member=None)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("ephemeral") is True


# ==============================================================================
# 6 & 7. Start Problem does NOT create Channel and does NOT create Thread
# ==============================================================================
@pytest.mark.asyncio
async def test_06_and_07_start_problem_does_not_create_channel_or_thread(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10001,
        uva_username="solver_1",
        uva_user_id=8881,
    )
    problem = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    service = ProblemService()
    view = ProblemSelectionView(problem, service)

    interaction = AsyncMock(spec=discord.Interaction)
    interaction.user.id = 10001
    interaction.user.name = "solver_1"
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()

    with patch("app.bot.views.problem_view.get_db_session") as mock_db, \
         patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=1234)):
        mock_db.return_value.__aenter__.return_value = async_db_session
        await view.start_button.callback(interaction)

    # Verify no channel or thread creation functions were ever invoked
    assert not interaction.guild.create_text_channel.called
    assert not interaction.channel.create_thread.called

    # Followup sent was ephemeral
    assert interaction.followup.send.called
    assert interaction.followup.send.call_args.kwargs.get("ephemeral") is True


# ==============================================================================
# 8. Active Session correctly created
# ==============================================================================
@pytest.mark.asyncio
async def test_08_active_session_correctly_created(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10002,
        uva_username="solver_2",
        uva_user_id=8882,
    )
    problem = Problem(problem_number=10041, title="Vito", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    service = ProblemService()
    with patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=99000)):
        session_obj, is_new = await service.start_problem_session(
            session=async_db_session,
            discord_user_id=10002,
            problem_number=10041,
        )

    assert is_new is True
    assert session_obj.status == "active"
    assert session_obj.thread_id is None
    assert session_obj.last_submission_id == 99000
    assert session_obj.user_id == user.id
    assert session_obj.problem_id == problem.id


# ==============================================================================
# 9. Duplicate Active Session is prevented and conflict handled
# ==============================================================================
@pytest.mark.asyncio
async def test_09_duplicate_active_session_prevented_and_conflict_handled(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10003,
        uva_username="solver_3",
        uva_user_id=8883,
    )
    p1 = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    p2 = Problem(problem_number=10041, title="Vito", difficulty="⭐")
    async_db_session.add_all([p1, p2])
    await async_db_session.flush()

    service = ProblemService()
    with patch.object(SubmissionProvider, "get_latest_submission_id", new=AsyncMock(return_value=1000)):
        s1, is_new = await service.start_problem_session(
            session=async_db_session,
            discord_user_id=10003,
            problem_number=100,
        )
    assert is_new is True

    # 1. Starting SAME problem again returns existing session without duplicate
    s1_dup, is_new_dup = await service.start_problem_session(
        session=async_db_session,
        discord_user_id=10003,
        problem_number=100,
    )
    assert is_new_dup is False
    assert s1_dup.id == s1.id

    # 2. Starting DIFFERENT problem raises ActiveSessionConflictException
    with pytest.raises(ActiveSessionConflictException) as exc_info:
        await service.start_problem_session(
            session=async_db_session,
            discord_user_id=10003,
            problem_number=10041,
        )
    assert exc_info.value.active_session.id == s1.id

    # Verify original session was NOT overwritten
    active_after = await service.get_active_session_by_user(async_db_session, 10003)
    assert active_after.problem_id == p1.id


# ==============================================================================
# 10. Submission correctly written to DB
# ==============================================================================
@pytest.mark.asyncio
async def test_10_submission_correctly_written_to_db(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10004,
        uva_username="solver_4",
        uva_user_id=8884,
    )
    problem = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    sub = await SubmissionRepository.record_submission(
        session=async_db_session,
        user_id=user.id,
        problem_id=problem.id,
        external_submission_id=777777,
        verdict="Wrong Answer",
        runtime=12,
    )
    assert sub.id is not None
    assert sub.external_submission_id == 777777

    # Query from DB
    loaded = await SubmissionRepository.get_by_external_id(async_db_session, 777777)
    assert loaded is not None
    assert loaded.verdict == "Wrong Answer"
    assert loaded.runtime == 12


# ==============================================================================
# 11. Submission NOT posted publicly to practice channel
# ==============================================================================
@pytest.mark.asyncio
async def test_11_submission_never_posted_publicly_to_practice_channel():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    mock_user = AsyncMock()
    mock_channel = AsyncMock()
    bot.get_user.return_value = mock_user
    bot.get_channel.return_value = mock_channel

    tracker = SubmissionTracker(bot)
    tracker.track_submissions.cancel()

    notif = SubmissionNotification(
        session_id=1,
        discord_user_id=10005,
        problem_number=100,
        problem_title="3n+1",
        submission_id=55555,
        language="C++",
        verdict="Wrong Answer",
        display_verdict="❌ Wrong Answer",
        runtime=10,
        attempts=1,
        is_accepted=False,
        started_at=datetime.now(timezone.utc),
    )

    await tracker._dispatch_notification(notif)

    # Sent to user via DM
    assert mock_user.send.called
    # NEVER sent to channel!
    assert not mock_channel.send.called


# ==============================================================================
# 12. DM notification normal
# ==============================================================================
@pytest.mark.asyncio
async def test_12_dm_notification_normal():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    mock_user = AsyncMock()
    bot.get_user.return_value = mock_user

    tracker = SubmissionTracker(bot)
    tracker.track_submissions.cancel()

    notif_ac = SubmissionNotification(
        session_id=1,
        discord_user_id=10006,
        problem_number=100,
        problem_title="The 3n + 1 Problem",
        submission_id=66666,
        language="C++11",
        verdict="Accepted",
        display_verdict="✅ Accepted",
        runtime=10,
        attempts=4,
        is_accepted=True,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=24),
        solved_at=datetime.now(timezone.utc),
    )

    await tracker._dispatch_notification(notif_ac)
    assert mock_user.send.called
    embed = mock_user.send.call_args.kwargs.get("embed")
    assert embed.title == "✅ Accepted!"
    assert "UVa 100" in embed.description
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Attempts"] == "4"
    assert "24 分鐘" in fields["作答時間"]
    assert fields["Submission ID"] == "66666"
    assert fields["語言"] == "C++11"


# ==============================================================================
# 13. DM Forbidden does not crash Tracker
# ==============================================================================
@pytest.mark.asyncio
async def test_13_dm_forbidden_does_not_crash_tracker():
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    mock_user = AsyncMock()
    mock_res = MagicMock()
    mock_res.status = 403
    mock_user.send.side_effect = discord.Forbidden(mock_res, "Cannot send DM")
    bot.get_user.return_value = mock_user

    tracker = SubmissionTracker(bot)
    tracker.track_submissions.cancel()

    notif = SubmissionNotification(
        session_id=1,
        discord_user_id=10007,
        problem_number=100,
        problem_title="3n+1",
        submission_id=77777,
        language="C++",
        verdict="Accepted",
        display_verdict="✅ Accepted",
        runtime=10,
        attempts=1,
        is_accepted=True,
        started_at=datetime.now(timezone.utc),
    )

    # Must execute smoothly without raising
    await tracker._dispatch_notification(notif)


# ==============================================================================
# 14. Accepted correctly creates UserSolvedProblem
# ==============================================================================
@pytest.mark.asyncio
async def test_14_accepted_correctly_creates_user_solved_problem(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10008,
        uva_username="solver_8",
        uva_user_id=8888,
    )
    problem = Problem(problem_number=100, uhunt_pid=36, title="3n+1", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    active_session = await SessionRepository.create_session(
        session=async_db_session,
        user_id=user.id,
        problem_id=problem.id,
        last_submission_id=100,
    )
    loaded = await SessionRepository.get_active_session(async_db_session, user.id, problem.id)

    mock_provider = MagicMock(spec=SubmissionProvider)
    mock_provider.get_user_submissions_since = AsyncMock(return_value=[
        SubmissionData(
            submission_id=105,
            uhunt_pid=36,
            verdict_id=90,  # Accepted
            runtime=10,
            submission_time=1700000000,
            language_id=3,
        )
    ])

    service = SubmissionService(provider=mock_provider)
    notifs = await service.check_session_submissions(async_db_session, loaded)

    assert len(notifs) == 1
    assert notifs[0].is_accepted is True
    assert loaded.status == "solved"

    # Check UserSolvedProblem exists
    solved = await SolvedRepository.get_user_solved_problems(async_db_session, user.id)
    assert len(solved) == 1
    assert solved[0].problem_id == problem.id


# ==============================================================================
# 15. Duplicate AC does not increment solved count
# ==============================================================================
@pytest.mark.asyncio
async def test_15_duplicate_ac_does_not_increment_solved_count(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10009,
        uva_username="solver_9",
        uva_user_id=8889,
    )
    problem = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    # First AC
    s1 = await SolvedRepository.record_solved(async_db_session, user.id, problem.id)
    assert s1 is not None

    # Second AC for same user + problem
    s2 = await SolvedRepository.record_solved(async_db_session, user.id, problem.id)
    assert s2.id == s1.id

    solved = await SolvedRepository.get_user_solved_problems(async_db_session, user.id)
    assert len(solved) == 1


# ==============================================================================
# 16. Restart does not re-notify old submissions
# ==============================================================================
@pytest.mark.asyncio
async def test_16_restart_does_not_re_notify_old_submissions(async_db_session):
    user = await UserRepository.link_uva(
        session=async_db_session,
        discord_user_id=10010,
        uva_username="solver_10",
        uva_user_id=8890,
    )
    problem = Problem(problem_number=100, uhunt_pid=36, title="3n+1", difficulty="⭐")
    async_db_session.add(problem)
    await async_db_session.flush()

    # Session started with last_submission_id = 5000
    active_session = await SessionRepository.create_session(
        session=async_db_session,
        user_id=user.id,
        problem_id=problem.id,
        last_submission_id=5000,
    )
    loaded = await SessionRepository.get_active_session(async_db_session, user.id, problem.id)

    # Provider returns empty when querying with min_sub_id=5000 because all subs are <= 5000
    mock_provider = MagicMock(spec=SubmissionProvider)
    mock_provider.get_user_submissions_since = AsyncMock(return_value=[])

    service = SubmissionService(provider=mock_provider)
    notifs = await service.check_session_submissions(async_db_session, loaded)

    assert len(notifs) == 0
    mock_provider.get_user_submissions_since.assert_called_once_with(
        uva_user_id=8890,
        min_sub_id=5000,
    )


# ==============================================================================
# 17. User A cannot access User B's private practice data
# ==============================================================================
@pytest.mark.asyncio
async def test_17_user_a_cannot_access_user_b_private_data(async_db_session):
    user_a = await UserRepository.link_uva(async_db_session, 111, "shen", 101)
    user_b = await UserRepository.link_uva(async_db_session, 222, "kevin", 102)

    p1 = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    p2 = Problem(problem_number=10041, title="Vito", difficulty="⭐")
    async_db_session.add_all([p1, p2])
    await async_db_session.flush()

    # Shen solves p1
    await SessionRepository.create_session(async_db_session, user_a.id, p1.id)
    await SolvedRepository.record_solved(async_db_session, user_a.id, p1.id)

    # Kevin solves p2
    await SessionRepository.create_session(async_db_session, user_b.id, p2.id)
    await SolvedRepository.record_solved(async_db_session, user_b.id, p2.id)

    problem_service = ProblemService()
    submission_service = SubmissionService()

    # Shen's queries
    shen_active = await problem_service.get_active_session_by_user(async_db_session, 111)
    shen_solved = await submission_service.get_user_solved(async_db_session, 111)

    # Kevin's queries
    kevin_active = await problem_service.get_active_session_by_user(async_db_session, 222)
    kevin_solved = await submission_service.get_user_solved(async_db_session, 222)

    assert shen_active.problem_id == p1.id
    assert kevin_active.problem_id == p2.id
    assert len(shen_solved) == 1 and shen_solved[0][0] == 100
    assert len(kevin_solved) == 1 and kevin_solved[0][0] == 10041


# ==============================================================================
# 18. Fixed Practice Center Message can be reused after restart
# ==============================================================================
@pytest.mark.asyncio
async def test_18_practice_center_message_reuse_and_recreate(async_db_session):
    # Setup guild settings with practice channel
    guild_id = 998877
    chan_id = 554433
    await GuildRepository.update_channels(async_db_session, guild_id, practice_channel_id=chan_id)

    bot = MagicMock()
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_existing_msg = AsyncMock(spec=discord.Message)
    mock_existing_msg.id = 123456
    mock_channel.fetch_message = AsyncMock(return_value=mock_existing_msg)
    bot.get_channel.return_value = mock_channel

    # Set existing message_id in DB
    await GuildRepository.update_practice_message_id(async_db_session, guild_id, 123456)

    # 1. Restart simulation: message exists -> edit / reuse
    with patch("app.bot.commands.setup_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        msg_id = await deploy_or_sync_practice_center(bot, guild_id)

    assert msg_id == 123456
    assert mock_existing_msg.edit.called
    assert not mock_channel.send.called

    # 2. Restart simulation: message was deleted -> recreate & update DB
    mock_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Message not found"))
    mock_new_msg = AsyncMock(spec=discord.Message)
    mock_new_msg.id = 789012
    mock_channel.send = AsyncMock(return_value=mock_new_msg)

    with patch("app.bot.commands.setup_cog.get_db_session") as mock_db:
        mock_db.return_value.__aenter__.return_value = async_db_session
        new_msg_id = await deploy_or_sync_practice_center(bot, guild_id)

    assert new_msg_id == 789012
    assert mock_channel.send.called
    settings = await GuildRepository.get_by_id(async_db_session, guild_id)
    assert settings.practice_message_id == 789012
