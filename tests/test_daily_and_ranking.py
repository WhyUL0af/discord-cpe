from datetime import date, datetime, timedelta, timezone
import pytest

from app.models.problem import Problem
from app.models.solved import UserSolvedProblem
from app.models.submission import Submission
from app.models.user import User
from app.repositories.ranking_repo import RankingRepository
from app.repositories.solved_repo import SolvedRepository
from app.repositories.submission_repo import SubmissionRepository
from app.repositories.user_repo import UserRepository
from app.services.daily_service import DailyService
from app.services.ranking_service import RankingService, get_start_of_week


@pytest.mark.asyncio
async def test_daily_problem_restart_safety(async_db_session):
    # Seed a problem
    prob = Problem(problem_number=100, title="3n+1", difficulty="⭐")
    async_db_session.add(prob)
    await async_db_session.flush()

    daily_service = DailyService()
    today = date(2026, 9, 23)

    daily1, num1 = await daily_service.get_or_create_daily_problem(async_db_session, target_date=today)
    assert daily1 is not None
    assert num1 >= 1

    # Simulated bot restart: fetch again for today
    daily2, num2 = await daily_service.get_or_create_daily_problem(async_db_session, target_date=today)
    assert daily2.id == daily1.id
    assert daily2.problem_id == daily1.problem_id
    assert num2 == num1


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
