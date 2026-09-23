import logging
import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from app.database import get_db_session
from app.models.guild import GuildSettings
from app.services.ranking_service import RankingService

logger = logging.getLogger(__name__)


class RankingUpdaterTask(commands.Cog):
    """Periodically updates the persistent leaderboard message in ranking channels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ranking_service = RankingService()
        self.update_leaderboard.start()

    def cog_unload(self) -> None:
        self.update_leaderboard.cancel()

    @tasks.loop(seconds=60)
    async def update_leaderboard(self) -> None:
        """Update leaderboard in each configured guild's ranking channel using message.edit()."""
        try:
            async with get_db_session() as session:
                ranking, total_subs, ac_subs = await self.ranking_service.get_weekly_ranking_data(
                    session=session,
                    limit=10,
                )
                embed = self.ranking_service.format_ranking_embed(
                    ranking=ranking,
                    title="🏆 Weekly CPE Ranking",
                    stats_footer=(total_subs, ac_subs),
                )

                stmt = select(GuildSettings).where(GuildSettings.ranking_channel_id.isnot(None))
                result = await session.execute(stmt)
                guild_configs = result.scalars().all()

                for cfg in guild_configs:
                    channel = self.bot.get_channel(cfg.ranking_channel_id)
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(cfg.ranking_channel_id)
                        except Exception:
                            continue

                    if not isinstance(channel, discord.TextChannel):
                        continue

                    message_edited = False
                    if cfg.ranking_message_id:
                        try:
                            msg = await channel.fetch_message(cfg.ranking_message_id)
                            await msg.edit(embed=embed)
                            message_edited = True
                        except discord.NotFound:
                            # Message was deleted by user, will repost below
                            cfg.ranking_message_id = None
                        except Exception as e:
                            logger.warning(f"Failed to edit ranking message in guild {cfg.guild_id}: {e}")

                    if not message_edited:
                        try:
                            new_msg = await channel.send(embed=embed)
                            cfg.ranking_message_id = new_msg.id
                            await session.flush()
                            logger.info(f"Initialized new persistent ranking message in guild {cfg.guild_id}")
                        except Exception as e:
                            logger.error(f"Failed to send ranking message in guild {cfg.guild_id}: {e}")

        except Exception as e:
            logger.error(f"Error in ranking updater loop: {e}", exc_info=True)

    @update_leaderboard.before_loop
    async def before_update_leaderboard(self) -> None:
        await self.bot.wait_until_ready()
        logger.info("RankingUpdaterTask started.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RankingUpdaterTask(bot))
