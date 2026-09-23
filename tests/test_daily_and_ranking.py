import asyncio
from datetime import date, datetime, timedelta, timezone
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.daily import DailyProblem
from app.models.problem import Problem
from app.models.solved import UserSolvedProblem
from app.models.submission import Submission
from app.models.user import User
from app.repositories.daily_repo import DailyRepository
from app.repositories.ranking_repo import RankingRepository
from app.repositories.solved_repo import SolvedRepository
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.user_repo import UserRepository
from app.services.daily_service import DailyService
from app.services.ranking_service import RankingService, get_start_of_week


@pytest.mark.asyncio
async def test_daily_problem_lifecycle_and_eager_loading(async_db_session):
    """Verify:
    1. First run creates DailyProblem with eager-loaded Problem.
    2. Second run retrieves the same DailyProblem without re-randomizing.
    3. Accessing daily.problem never raises MissingGreenlet.
    4. Database enforces UNIQUE constraint on (guild_id, date).
    """
    daily_service = DailyService()
    today = date(2026, 9, 23)
    guild_id = 123456789

    # 1. First execution: creates DailyProblem
    daily1, num1 = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_id,
        target_date=today,
    )
    assert daily1 is not None
    assert daily1.guild_id == guild_id
    assert daily1.date == today
    assert num1 >= 1

    # Verify relationship eager-loading without MissingGreenlet
    assert daily1.problem is not None
    assert daily1.problem.problem_number > 0
    assert isinstance(daily1.problem.title, str)

    # 2. Second execution: retrieves exact same problem
    daily2, num2 = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_id,
        target_date=today,
    )
    assert daily2.id == daily1.id
    assert daily2.problem_id == daily1.problem_id
    assert daily2.problem.problem_number == daily1.problem.problem_number
    assert num2 == num1

    # 3. Constraint test: trying to directly insert another record for the same guild & date fails
    with pytest.raises(IntegrityError):
        async with async_db_session.begin_nested():
            duplicate = DailyProblem(
                guild_id=guild_id,
                date=today,
                problem_id=daily1.problem_id,
            )
            async_db_session.add(duplicate)
            await async_db_session.flush()


@pytest.mark.asyncio
async def test_daily_problem_restart_simulation(async_db_session):
    """Simulate bot restart: close/clear session and verify problem remains identical."""
    daily_service = DailyService()
    today = date(2026, 9, 24)
    guild_id = 987654321

    # Before restart
    daily_before, _ = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_id,
        target_date=today,
    )
    chosen_problem_number = daily_before.problem.problem_number

    # Simulate restart by expiring session cache
    async_db_session.expire_all()

    # After restart
    daily_after, _ = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_id,
        target_date=today,
    )
    assert daily_after.id == daily_before.id
    assert daily_after.problem.problem_number == chosen_problem_number
    # Access problem properties directly without lazy IO exception
    assert daily_after.problem.title == daily_before.problem.title


@pytest.mark.asyncio
async def test_daily_problem_multi_guild_sync(async_db_session):
    """Verify that multiple guilds on the same date share the same selected problem."""
    daily_service = DailyService()
    today = date(2026, 9, 25)
    guild_a = 111111111
    guild_b = 222222222

    daily_a, _ = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_a,
        target_date=today,
    )
    daily_b, _ = await daily_service.get_or_create_daily_problem(
        session=async_db_session,
        guild_id=guild_b,
        target_date=today,
    )

    # Different records per guild with unique IDs
    assert daily_a.id != daily_b.id
    assert daily_a.guild_id == guild_a
    assert daily_b.guild_id == guild_b
    # But sharing the synchronized problem for the date
    assert daily_a.problem_id == daily_b.problem_id
    assert daily_a.problem.problem_number == daily_b.problem.problem_number


@pytest.mark.asyncio
async def test_ranking_deduplication_and_ordering(async_db_session):
    # Setup users
    user_alex = await UserRepository.link_uva(async_db_session, 1001, "alex", 101)
    user_shen = await UserRepository.link_uva(async_db_session, 1002, "shen", 102)

    # Setup problems
    prob1 = Problem(problem_number=100, title="P100", difficulty="⭐")
    prob2 = Problem(problem_number=272, title="P272", difficulty="⭐")
    async_db_session.add_all([prob1, prob2])
    await async_db_session.flush()

    now = datetime.now(timezone.utc)

    # Alex solves prob1 and prob2 (2 AC)
    await SolvedRepository.record_solved(async_db_session, user_alex.id, prob1.id, now)
    await SolvedRepository.record_solved(async_db_session, user_alex.id, prob2.id, now)

    # Shen solves prob1 only (1 AC)
    await SolvedRepository.record_solved(async_db_session, user_shen.id, prob1.id, now)

    # Shen submits prob1 again multiple times -> SolvedRepository.record_solved must not duplicate!
    await SolvedRepository.record_solved(async_db_session, user_shen.id, prob1.id, now)

    # Verify rankings
    ranking = await RankingRepository.get_all_time_ranking(async_db_session)
    assert len(ranking) == 2
    assert ranking[0][0].id == user_alex.id
    assert ranking[0][1] == 2  # Alex has 2 AC
    assert ranking[1][0].id == user_shen.id
    assert ranking[1][1] == 1  # Shen has 1 AC despite multiple attempts!


@pytest.mark.asyncio
async def test_ranking_service_format():
    user = User(discord_user_id=123456, uva_username="alex")
    ranking_data = [(user, 15)]
    embed = RankingService.format_ranking_embed(
        ranking=ranking_data,
        title="🏆 Weekly CPE Ranking",
        stats_footer=(120, 45)
    )

    assert "🏆 Weekly CPE Ranking" in embed.title
    assert "15 AC" in embed.description
    assert "<@123456>" in embed.description
    assert "120" in embed.fields[0].value
    assert "45" in embed.fields[0].value
