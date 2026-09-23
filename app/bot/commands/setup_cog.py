import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.services.guild_service import GuildService

logger = logging.getLogger(__name__)


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_service = GuildService()

    @app_commands.command(name="setup", description="設定 CPE Bot 於此伺服器的各功能頻道（僅管理員可用）")
    @app_commands.describe(
        daily_channel="🎯・每日一題 發布頻道",
        practice_channel="💻・刷題區 頻道（使用者取得題目與開啟 Thread 的入口）",
        ranking_channel="🏆・排行榜 頻道（常駐排行榜訊息）",
        discussion_channel="💬・題目討論 頻道",
        archive_on_solve="當題目 Accepted (AC) 後是否自動封存 Thread（預設 False）",
    )
    @app_commands.default_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        daily_channel: Optional[discord.TextChannel] = None,
        practice_channel: Optional[discord.TextChannel] = None,
        ranking_channel: Optional[discord.TextChannel] = None,
        discussion_channel: Optional[discord.TextChannel] = None,
        archive_on_solve: Optional[bool] = None,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("❌ 此指令僅限在 Discord 伺服器中使用。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            # If all are None, just show current config
            if (
                daily_channel is None
                and practice_channel is None
                and ranking_channel is None
                and discussion_channel is None
                and archive_on_solve is None
            ):
                settings = await self.guild_service.get_settings(session, interaction.guild_id)
            else:
                settings = await self.guild_service.configure_channels(
                    session=session,
                    guild_id=interaction.guild_id,
                    daily_channel_id=daily_channel.id if daily_channel else None,
                    practice_channel_id=practice_channel.id if practice_channel else None,
                    ranking_channel_id=ranking_channel.id if ranking_channel else None,
                    discussion_channel_id=discussion_channel.id if discussion_channel else None,
                    archive_thread_on_solve=archive_on_solve,
                )

            embed = discord.Embed(
                title="⚙️ CPE Discord Bot 伺服器設定",
                description=f"伺服器：**{interaction.guild.name}** (`{interaction.guild_id}`)",
                color=discord.Color.gold(),
            )

            def channel_mention(cid: Optional[int]) -> str:
                return f"<#{cid}>" if cid else "*未設定*"

            embed.add_field(name="🎯 每日一題頻道：", value=channel_mention(settings.daily_channel_id), inline=False)
            embed.add_field(name="💻 刷題區頻道：", value=channel_mention(settings.practice_channel_id), inline=False)
            embed.add_field(name="🏆 排行榜頻道：", value=channel_mention(settings.ranking_channel_id), inline=False)
            embed.add_field(name="💬 題目討論頻道：", value=channel_mention(settings.discussion_channel_id), inline=False)
            embed.add_field(name="📦 AC 後自動封存 Thread：", value="是" if settings.archive_thread_on_solve else "否", inline=False)

            embed.set_footer(text="可重複使用 /setup 傳入參數進行設定更新。")
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
