import logging
from typing import Literal
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.services.ranking_service import RankingService

logger = logging.getLogger(__name__)


class RankCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ranking_service = RankingService()

    @app_commands.command(name="rank", description="查看 CPE 解題排行榜（本週或歷史）")
    @app_commands.describe(scope="排行榜範圍：weekly（本週排名）或 all（歷史總排名）")
    async def rank(
        self,
        interaction: discord.Interaction,
        scope: Literal["weekly", "all"] = "weekly"
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        async with get_db_session() as session:
            if scope == "weekly":
                ranking, total_subs, ac_subs = await self.ranking_service.get_weekly_ranking_data(
                    session=session,
                    limit=10,
                )
                embed = self.ranking_service.format_ranking_embed(
                    ranking=ranking,
                    title="🏆 Weekly CPE Ranking",
                    stats_footer=(total_subs, ac_subs),
                )
            else:
                ranking = await self.ranking_service.get_all_time_ranking_data(
                    session=session,
                    limit=15,
                )
                embed = self.ranking_service.format_ranking_embed(
                    ranking=ranking,
                    title="🏆 All-Time CPE Solved Ranking",
                )

            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankCog(bot))
