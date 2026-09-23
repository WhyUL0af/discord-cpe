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
            f"Submission detected for user {notif.discord_user_id} on UVa {notif.problem_number}: verdict={notif.verdict}"
        )

        try:
            channel = self.bot.get_channel(notif.thread_id)
            if not channel:
                channel = await self.bot.fetch_channel(notif.thread_id)

            if not isinstance(channel, discord.Thread):
                logger.warning(f"Channel {notif.thread_id} is not a Thread.")
                return

            if notif.is_accepted:
                embed = discord.Embed(
                    title="✅ Accepted",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Problem：", value=f"UVa {notif.problem_number} - {notif.problem_title}", inline=False)
                embed.add_field(name="User：", value=f"<@{notif.discord_user_id}>", inline=True)
                embed.add_field(name="Attempts：", value=str(notif.attempts), inline=True)
                if notif.runtime is not None:
                    embed.add_field(name="Runtime：", value=f"{notif.runtime} ms", inline=True)
                embed.set_footer(text="恭喜解題成功！本題已列入個人解題清單與排行榜。")

                await channel.send(content=f"🎉 恭喜 <@{notif.discord_user_id}> AC！", embed=embed)

                # Update thread name to indicate solved
                new_name = f"✅ UVa {notif.problem_number}｜{channel.name.split('｜')[-1]}"
                try:
                    await channel.edit(name=new_name[:100])
                except Exception as e:
                    logger.warning(f"Could not rename thread {channel.id}: {e}")

                # Check auto-archive configuration
                if settings.AUTO_ARCHIVE_THREAD:
                    try:
                        await channel.edit(archived=True)
                    except Exception as e:
                        logger.warning(f"Could not auto-archive thread {channel.id}: {e}")

            elif notif.verdict == "In queue":
                embed = discord.Embed(
                    title="⏳ Submission detected",
                    description=f"**UVa {notif.problem_number}** - {notif.problem_title}\n\nStatus：Judging...",
                    color=discord.Color.gold(),
                )
                await channel.send(embed=embed)

            else:
                # Other verdicts: Wrong Answer, Time Limit Exceeded, Compilation Error, etc.
                embed = discord.Embed(
                    title=notif.display_verdict,
                    color=discord.Color.red(),
                )
                embed.add_field(name="Problem：", value=f"UVa {notif.problem_number}", inline=False)
                embed.add_field(name="User：", value=f"<@{notif.discord_user_id}>", inline=True)
                embed.add_field(name="Attempts：", value=str(notif.attempts), inline=True)
                if notif.runtime is not None and notif.runtime > 0:
                    embed.add_field(name="Runtime：", value=f"{notif.runtime} ms", inline=True)
                embed.set_footer(text="不要氣餒，檢查邏輯或測資後再次提交！")

                await channel.send(embed=embed)

        except discord.NotFound:
            logger.warning(f"Thread {notif.thread_id} not found on Discord.")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permissions to post in thread {notif.thread_id}.")
        except Exception as e:
            logger.error(f"Failed to post submission notification to thread {notif.thread_id}: {e}", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SubmissionTracker(bot))
