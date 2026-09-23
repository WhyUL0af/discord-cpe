import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.services.guild_service import GuildService
from app.bot.views.problem_view import PracticeCenterView, create_practice_center_embed

logger = logging.getLogger(__name__)


class SetupCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_service = GuildService()

    async def _deploy_practice_center(
        self,
        session,
        guild: discord.Guild,
        practice_channel: discord.TextChannel,
        current_msg_id: Optional[int],
    ) -> Optional[int]:
        """Deploy or update the persistent practice center message."""
        center_embed = create_practice_center_embed()
        center_view = PracticeCenterView()

        msg = None
        if current_msg_id:
            try:
                msg = await practice_channel.fetch_message(current_msg_id)
                await msg.edit(embed=center_embed, view=center_view)
                logger.info(f"Updated persistent practice center message {current_msg_id} in {practice_channel.id}")
            except Exception:
                msg = None

        if not msg:
            try:
                msg = await practice_channel.send(embed=center_embed, view=center_view)
                await self.guild_service.set_practice_message(session, guild.id, msg.id)
                logger.info(f"Posted new persistent practice center message {msg.id} in {practice_channel.id}")
            except Exception as e:
                logger.warning(f"Could not post practice center message to channel {practice_channel.id}: {e}")
                return None

        return msg.id

    @app_commands.command(name="setup", description="設定 CPE Bot 於此伺服器的各功能頻道（僅管理員可用）")
    @app_commands.describe(
        daily_channel="🎯・每日一題 發布頻道",
        practice_channel="💻・刷題區 頻道（常駐 CPE 刷題中心訊息入口）",
        ranking_channel="🏆・排行榜 頻道（常駐排行榜訊息）",
        discussion_channel="💬・題目討論 頻道",
        archive_on_solve="當題目 Accepted (AC) 後是否自動封存（預設 False）",
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
        if not interaction.guild_id or not interaction.guild:
            await interaction.response.send_message("❌ 此指令僅限在 Discord 伺服器中使用。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
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

            # Auto-deploy or update practice center message if practice channel is configured
            if settings.practice_channel_id:
                p_chan = interaction.guild.get_channel(settings.practice_channel_id)
                if not p_chan:
                    try:
                        p_chan = await interaction.guild.fetch_channel(settings.practice_channel_id)
                    except Exception:
                        p_chan = None

                if isinstance(p_chan, discord.TextChannel):
                    await self._deploy_practice_center(
                        session=session,
                        guild=interaction.guild,
                        practice_channel=p_chan,
                        current_msg_id=settings.practice_message_id,
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

            embed.set_footer(text="可重複使用 /setup 傳入參數進行設定更新。刷題中心已在刷題區就緒。")
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="practice_center", description="在刷題區重新發布或更新常駐「CPE 刷題中心」訊息（僅管理員可用）")
    @app_commands.default_permissions(administrator=True)
    async def practice_center(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id or not interaction.guild:
            await interaction.response.send_message("❌ 此指令僅限在 Discord 伺服器中使用。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            settings = await self.guild_service.get_settings(session, interaction.guild_id)
            if not settings.practice_channel_id:
                await interaction.followup.send("⚠️ 尚未設定刷題區頻道，請先使用 `/setup practice_channel:#頻道` 設定。", ephemeral=True)
                return

            p_chan = interaction.guild.get_channel(settings.practice_channel_id)
            if not p_chan:
                try:
                    p_chan = await interaction.guild.fetch_channel(settings.practice_channel_id)
                except Exception:
                    p_chan = None

            if not isinstance(p_chan, discord.TextChannel):
                await interaction.followup.send("❌ 找不到設定的刷題區文字頻道。", ephemeral=True)
                return

            msg_id = await self._deploy_practice_center(
                session=session,
                guild=interaction.guild,
                practice_channel=p_chan,
                current_msg_id=settings.practice_message_id,
            )

            if msg_id:
                await interaction.followup.send(f"✅ 已成功在 <#{p_chan.id}> 發布/更新「CPE 刷題中心」常駐訊息！", ephemeral=True)
            else:
                await interaction.followup.send("❌ 發布訊息失敗，請確認機器人擁有該頻道的發言與嵌入權限。", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
