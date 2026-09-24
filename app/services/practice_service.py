import logging
from typing import Optional
import discord

from app.models.problem import Problem
from app.services.problem_service import ProblemService
from app.bot.views.problem_view import start_problem_for_user

logger = logging.getLogger(__name__)


class PracticeService:
    """Service providing unified problem-solving workflow and session management."""

    @staticmethod
    async def start_problem(
        interaction: discord.Interaction,
        problem: Optional[Problem] = None,
        problem_number: Optional[int] = None,
        problem_service: Optional[ProblemService] = None,
        is_daily: bool = False,
    ) -> None:
        """Initiate problem solving for the user through the shared workflow."""
        await start_problem_for_user(
            interaction=interaction,
            problem=problem,
            problem_number=problem_number,
            problem_service=problem_service,
            is_daily=is_daily,
        )
