import asyncio
import logging
from discord.ext import commands, tasks
from sqlalchemy import select

from app.config import settings
from app.database import get_db_session
from app.models.user import User
from app.providers.problem_provider import CpeProblemProvider
from app.repositories.problem_repo import ProblemRepository
from app.services.external_submission_service import ExternalSubmissionService

logger = logging.getLogger(__name__)


class SubmissionTracker(commands.Cog):
    """Track external submissions for every linked user, without practice sessions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.submission_service = ExternalSubmissionService()
        self.pool_initialized = False
        self.poll_interval = max(5, settings.SUBMISSION_POLL_INTERVAL)
        self.track_submissions.change_interval(seconds=self.poll_interval)
        self.track_submissions.start()

    def cog_unload(self) -> None:
        self.track_submissions.cancel()

    @tasks.loop(seconds=20)
    async def track_submissions(self) -> None:
        """Poll linked users and save results. Never send Discord DMs."""
        try:
            async with get_db_session() as session:
                if not self.pool_initialized:
                    for data in await CpeProblemProvider().get_problems():
                        await ProblemRepository.upsert_from_data(session, data)
                user_ids = list((await session.scalars(select(User.id).where(User.uva_user_id.isnot(None)))).all())
            self.pool_initialized = True

            for user_id in user_ids:
                try:
                    async with get_db_session() as session:
                        user = await session.get(User, user_id)
                        if not user or not user.uva_user_id:
                            continue
                        notifications, checkpoint = await self.submission_service.sync_user(session, user)
                    self.submission_service.acknowledge(checkpoint)
                    if notifications:
                        logger.debug("Synced %s changed submissions for user %s", len(notifications), user_id)
                except Exception:
                    logger.exception("Error tracking external submissions for user %s", user_id)
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Error in submission tracker loop: {e}", exc_info=True)

    @track_submissions.before_loop
    async def before_track_submissions(self) -> None:
        await self.bot.wait_until_ready()
        logger.info(
            f"SubmissionTracker task started with polling interval {self.poll_interval}s"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SubmissionTracker(bot))
