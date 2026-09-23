from datetime import date
import logging
from typing import Optional
import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from app.database import get_db_session
from app.models.guild import GuildSettings
from app.models.problem import Problem
from app.services.daily_service import DailyService
from app.services.problem_service import ProblemService
from app.bot.views.problem_view import ProblemActionView

logger = logging.getLogger(__name__)


class DailyProblemView(discord.ui.View):
    def __init__(self, problem: Problem) -> None:
        super().__init__(timeout=None)
        self.problem = problem
        self.problem_service = ProblemService()
        self.daily_service = DailyService()

        # Link button
        if problem.external_url:
            self.add_item(
                discord.ui.Button(
                    label="📖 查看題目",
                    url=problem.external_url,
                    style=discord.ButtonStyle.link,
                )
            )

    @discord.ui.button(
        label="💻 開始作答",
        style=discord.ButtonStyle.success,
        custom_id="cpe_daily_start_problem_button",
    )
    async def start_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        # Delegate to standard ProblemActionView logic
        view = ProblemActionView(self.problem, self.problem_service)
        await view.start_button(interaction, button)

    @discord.ui.button(
        label="📊 查看統計",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_daily_stats_button",
    )
    async def stats_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            solved_today = await self.daily_service.count_solved_today(
                session, self.problem.id
            )
            embed = discord.Embed(
                title=f"📊 今日解題統計：UVa {self.problem.problem_number}",
                description=f"今日已有 **{solved_today}** 位成員成功解答 (AC)！",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class DailyProblemTask(commands.Cog):
    """Periodically checks and posts the Daily Problem into configured daily channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_service = DailyService()
        self.last_posted_date: Optional[date] = None
        self.daily_loop.start()

    def cog_unload(self) -> None:
        self.daily_loop.cancel()

    @tasks.loop(minutes=10)
    async def daily_loop(self) -> None:
        """Check every 10 minutes if today's daily problem needs to be posted."""
        today = date.today()
        if self.last_posted_date == today:
            return

        try:
            async with get_db_session() as session:
                daily, daily_number = await self.daily_service.get_or_create_daily_problem(
                    session=session,
                    target_date=today,
                )
                problem = daily.problem
                solved_today = await self.daily_service.count_solved_today(
                    session=session,
                    problem_id=problem.id,
                    target_date=today,
                )

                # Find all guilds with daily_channel_id configured
                stmt = select(GuildSettings).where(GuildSettings.daily_channel_id.isnot(None))
                result = await session.execute(stmt)
                guild_configs = result.scalars().all()

                for cfg in guild_configs:
                    channel = self.bot.get_channel(cfg.daily_channel_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(cfg.daily_channel_id)
                        except Exception:
                            continue

                    if not isinstance(channel, discord.TextChannel):
                        continue

                    # Check if already posted today in this guild channel
                    if daily.discord_message_id:
                        continue

                    embed = discord.Embed(
                        title=f"━━━━━━━━━━━━━━━━━━\nCPE DAILY #{daily_number}\n━━━━━━━━━━━━━━━━━━",
                        description=f"### 📘 UVa {problem.problem_number}\n**{problem.title}**",
                        color=discord.Color.orange(),
                    )
                    embed.add_field(name="Difficulty：", value=problem.difficulty or "Unknown", inline=True)
                    embed.add_field(name="Solved Today：", value=str(solved_today), inline=True)
                    embed.set_footer(text="點擊「💻 開始作答」建立專屬 Thread，前往 UVa 提交即可自動追蹤評測結果！")

                    view = DailyProblemView(problem)
                    msg = await channel.send(embed=embed, view=view)

                    daily.discord_message_id = msg.id
                    await session.flush()
                    logger.info(f"Posted Daily Problem #{daily_number} to channel {channel.id}")

            self.last_posted_date = today

        except Exception as e:
            logger.error(f"Error in daily problem task: {e}", exc_info=True)

    @daily_loop.before_loop
    async def before_daily_loop(self) -> None:
        await self.bot.wait_until_ready()
        logger.info("DailyProblemTask started.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyProblemTask(bot))
