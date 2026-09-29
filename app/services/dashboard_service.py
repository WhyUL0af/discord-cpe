"""Compose dashboard data without introducing another identity or ranking system."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Problem, Submission, User
from app.repositories.daily_repo import DailyRepository
from app.repositories.dashboard_repo import DashboardRepository
from app.services.ranking_service import RankingService


@dataclass
class DashboardData:
    solved: int
    total: int
    daily: Problem | None
    continue_problem: Problem | None
    recent: list[Submission]
    ranking: list[tuple[User, int]]


class DashboardService:
    @staticmethod
    async def get_dashboard(session: AsyncSession, user_id: int) -> DashboardData:
        solved, total = await DashboardRepository.progress(session, user_id)
        daily = await DailyRepository.get_any_by_date(session, date.today())
        return DashboardData(
            solved=solved, total=total, daily=daily.problem if daily else None,
            continue_problem=await DashboardRepository.continue_problem(session, user_id),
            recent=await DashboardRepository.recent_submissions(session, user_id),
            ranking=await RankingService.get_all_time_ranking_data(session, 5),
        )
