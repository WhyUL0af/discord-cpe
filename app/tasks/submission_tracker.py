import asyncio
import logging
from typing import Optional
import discord
from discord.ext import commands, tasks

from app.config import settings
from app.database import get_db_session
from app.repositories.session_repo import SessionRepository
from app.services.submission_service import SubmissionService, SubmissionNotification

logger = logging.getLogger(__name__)


class SubmissionTracker(commands.Cog):
    """Background task that tracks UVa submissions for active problem sessions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.submission_service = SubmissionService()
        self.poll_interval = max(5, settings.SUBMISSION_POLL_INTERVAL)
        self.track_submissions.change_interval(seconds=self.poll_interval)
        self.track_submissions.start()

    def cog_unload(self) -> None:
        self.track_submissions.cancel()

    @tasks.loop(seconds=20)
    async def track_submissions(self) -> None:
        """Periodic loop to poll uHunt for active problem sessions only."""
        try:
            async with get_db_session() as session:
                active_sessions = await SessionRepository.get_all_active_sessions(session)
                if not active_sessions:
                    return

                logger.debug(f"Tracking {len(active_sessions)} active problem session(s)...")

                for active_session in active_sessions:
                    try:
                        notifications = await self.submission_service.check_session_submissions(
                            session=session,
                            active_session=active_session,
                        )

                        for notif in notifications:
                            await self._dispatch_notification(notif)

                        # Small yield between sessions to respect rate limits
                        await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.error(
                            f"Error tracking session {active_session.id} for user {active_session.user_id}: {e}",
                            exc_info=True,
                        )

        except Exception as e:
            logger.error(f"Error in submission tracker loop: {e}", exc_info=True)

    @track_submissions.before_loop
    async def before_track_submissions(self) -> None:
        await self.bot.wait_until_ready()
        logger.info(
            f"SubmissionTracker task started with polling interval {self.poll_interval}s"
        )

    async def _dispatch_notification(self, notif: SubmissionNotification) -> None:
        logger.info(
            f"Submission detected for user {notif.discord_user_id} on UVa {notif.problem_number}: verdict={notif.verdict} (sub_id={notif.submission_id})"
        )

        try:
            user = self.bot.get_user(notif.discord_user_id)
            if not user:
                try:
                    user = await self.bot.fetch_user(notif.discord_user_id)
                except Exception as e:
                    logger.warning(f"Could not fetch user {notif.discord_user_id} for DM notification: {e}")
                    return

            if not user:
                logger.warning(f"User {notif.discord_user_id} not found.")
                return

            if notif.is_accepted:
                # Calculate elapsed solve time
                solve_time_str = "即時"
                if notif.started_at:
                    end_time = notif.solved_at or datetime.now(timezone.utc)
                    elapsed_seconds = max(0, int((end_time - notif.started_at).total_seconds()))
                    mins = elapsed_seconds // 60
                    hrs = mins // 60
                    if hrs > 0:
                        solve_time_str = f"{hrs} 小時 {mins % 60} 分鐘"
                    elif mins > 0:
                        solve_time_str = f"{mins} 分鐘"
                    else:
                        solve_time_str = f"{elapsed_seconds} 秒"

                embed = discord.Embed(
                    title="✅ Accepted!",
                    description=f"**UVa {notif.problem_number}**\n{notif.problem_title}",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Attempts", value=str(notif.attempts), inline=True)
                embed.add_field(name="作答時間", value=solve_time_str, inline=True)
                embed.add_field(name="Submission ID", value=str(notif.submission_id), inline=True)
                embed.add_field(name="語言", value=notif.language, inline=True)
                if notif.runtime is not None:
                    embed.add_field(name="執行時間", value=f"{notif.runtime} ms", inline=True)
                embed.set_footer(text="本題已自動計入解題紀錄與排行榜！")

            elif notif.verdict == "In queue":
                embed = discord.Embed(
                    title="⏳ In Queue",
                    description=f"**UVa {notif.problem_number}**\n{notif.problem_title}\n\n正在等待評測結果...",
                    color=discord.Color.gold(),
                )
                embed.add_field(name="Submission ID", value=str(notif.submission_id), inline=True)
                embed.add_field(name="語言", value=notif.language, inline=True)

            else:
                embed = discord.Embed(
                    title=notif.display_verdict,
                    description=f"**UVa {notif.problem_number}**\n{notif.problem_title}",
                    color=discord.Color.red(),
                )
                embed.add_field(name="Attempts", value=str(notif.attempts), inline=True)
                embed.add_field(name="Submission ID", value=str(notif.submission_id), inline=True)
                embed.add_field(name="語言", value=notif.language, inline=True)
                if notif.runtime is not None and notif.runtime > 0:
                    embed.add_field(name="執行時間", value=f"{notif.runtime} ms", inline=True)
                embed.set_footer(text="不要氣餒，檢查邏輯或測資後再次提交！")

            try:
                await user.send(embed=embed)
                logger.info(f"Dispatched DM to user {notif.discord_user_id} for UVa {notif.problem_number} ({notif.verdict})")
            except (discord.Forbidden, discord.HTTPException) as dm_err:
                logger.warning(
                    f"Could not send DM to user {notif.discord_user_id} (DM closed/blocked): {dm_err}"
                )

        except Exception as e:
            logger.error(
                f"Unexpected error in _dispatch_notification for user {notif.discord_user_id}: {e}",
                exc_info=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SubmissionTracker(bot))
