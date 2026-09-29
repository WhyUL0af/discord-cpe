from datetime import datetime, time
import logging
from typing import Optional
from zoneinfo import ZoneInfo
import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from app.database import get_db_session
from app.models.guild import GuildSettings
from app.models.problem import Problem
from app.services.daily_service import DailyService
from app.bot.views.problem_view import DailyProblemView

logger = logging.getLogger(__name__)
DAILY_TIMEZONE = ZoneInfo("Asia/Taipei")
DAILY_POST_TIME = time(7, 0, tzinfo=DAILY_TIMEZONE)



class DailyProblemTask(commands.Cog):
    """Periodically checks and posts the Daily Problem into configured daily channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_service = DailyService()
        self.daily_loop.start()

    def cog_unload(self) -> None:
        self.daily_loop.cancel()

    @tasks.loop(time=DAILY_POST_TIME)
    async def daily_loop(self) -> None:
        await self.post_due_daily_problem()

    async def post_due_daily_problem(self) -> None:
        """Post once per Taipei day after 07:00, including after a late restart."""
        now = datetime.now(DAILY_TIMEZONE)
        if now.hour < 7:
            return
        today = now.date()

        try:
            async with get_db_session() as session:
                # Find all guilds with daily_channel_id configured
                stmt = select(GuildSettings).where(GuildSettings.daily_channel_id.isnot(None))
                result = await session.execute(stmt)
                guild_configs = result.scalars().all()

                for cfg in guild_configs:
                    if not cfg.daily_channel_id:
                        continue

                    # 1. Fetch or create today's daily problem for this guild
                    daily, daily_number = await self.daily_service.get_or_create_daily_problem(
                        session=session,
                        guild_id=cfg.guild_id,
                        target_date=today,
                    )

                    # 2. Check if this guild has already posted today's message
                    if daily.discord_message_id:
                        continue

                    channel = self.bot.get_channel(cfg.daily_channel_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(cfg.daily_channel_id)
                        except Exception:
                            logger.warning(f"Could not reach channel {cfg.daily_channel_id} in guild {cfg.guild_id}")
                            continue

                    if not isinstance(channel, discord.TextChannel):
                        continue

                    # Eagerly loaded problem safely accessed without triggering async lazy IO
                    problem = daily.problem
                    solved_today = await self.daily_service.count_solved_today(
                        session=session,
                        problem_id=problem.id,
                        target_date=today,
                    )

                    embed = discord.Embed(
                        title=f"━━━━━━━━━━━━━━━━━━\nCPE DAILY #{daily_number}\n━━━━━━━━━━━━━━━━━━",
                        description=f"### 📘 UVa {problem.problem_number}\n**{problem.title}**",
                        color=discord.Color.orange(),
                    )
                    embed.add_field(name="Difficulty：", value=problem.difficulty or "Unknown", inline=True)
                    embed.add_field(name="Solved Today：", value=str(solved_today), inline=True)
                    embed.set_footer(text="自行至 UVa 提交；使用 /link 綁定帳號後，Bot 會透過 uHunt 追蹤結果與排行榜。")

                    view = DailyProblemView(problem)
                    msg = await channel.send(embed=embed, view=view)

                    daily.discord_message_id = msg.id
                    await session.flush()
                    logger.info(
                        f"Posted Daily Problem #{daily_number} (UVa {problem.problem_number}) to guild {cfg.guild_id} channel {channel.id}"
                    )

        except Exception as e:
            logger.error(f"Error in daily problem task: {e}", exc_info=True)

    @daily_loop.before_loop
    async def before_daily_loop(self) -> None:
        await self.bot.wait_until_ready()
        logger.info("DailyProblemTask started.")
        await self.post_due_daily_problem()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyProblemTask(bot))
