import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.config import settings
from app.services.user_service import UserService
from app.providers.uva_provider import (
    UvaUserNotFoundException,
    UvaApiException,
    UvaTimeoutException,
)

logger = logging.getLogger(__name__)


class AccountCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.user_service = UserService()

    async def _sync_linked_role(self, interaction: discord.Interaction, *, linked: bool) -> str:
        """Grant or revoke the configured role after the account change commits."""
        if not settings.DISCORD_LINKED_ROLE_ID:
            return "⚠️ 管理員尚未設定已綁定身分組。"
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return "⚠️ 請在 Discord 伺服器內執行此指令以同步身分組。"
        role = interaction.guild.get_role(settings.DISCORD_LINKED_ROLE_ID)
        if role is None:
            return "⚠️ 找不到已綁定身分組，請聯絡管理員檢查身分組 ID。"
        try:
            if linked and role not in interaction.user.roles:
                await interaction.user.add_roles(role, reason="UVa account linked")
            elif not linked and role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="UVa account unlinked")
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Could not sync linked role for user %s", interaction.user.id)
            return "⚠️ 身分組同步失敗，請管理員確認 Bot 的管理身分組權限及身分組順序。"
        return "✅ 已開放練習頻道。" if linked else "✅ 已移除練習頻道權限。"

    @app_commands.command(name="link", description="綁定你的 UVa Online Judge 帳號")
    @app_commands.describe(uva_username="你的 UVa Online Judge 使用者名稱")
    async def link(self, interaction: discord.Interaction, uva_username: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            async with get_db_session() as session:
                user, profile = await self.user_service.link_uva_account(
                    session=session,
                    discord_user_id=interaction.user.id,
                    uva_username=uva_username,
                    discord_username=interaction.user.name,
                )

                linked_username = user.uva_username
            role_result = await self._sync_linked_role(interaction, linked=True)
            embed = discord.Embed(
                title="🔗 UVa Account Linked",
                color=discord.Color.green(),
            )
            embed.add_field(name="Discord：", value=f"<@{interaction.user.id}>", inline=False)
            embed.add_field(name="UVa：", value=f"`{linked_username}`", inline=False)
            embed.add_field(name="頻道權限", value=role_result, inline=False)
            embed.set_footer(text="直接到 UVa 提交，再點「查看提交結果」取得私人回覆；排行榜自動更新，不發私訊。")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except UvaUserNotFoundException:
            await interaction.followup.send(
                f"❌ 找不到 UVa User：{uva_username}",
                ephemeral=True
            )
        except (UvaTimeoutException, UvaApiException):
            await interaction.followup.send(
                "⚠️ 暫時無法取得 UVa / uHunt 資料來源驗證帳號，請稍後再試。",
                ephemeral=True
            )
        except Exception as e:
            logger.exception(f"Unexpected error linking user {interaction.user.id}: {e}")
            await interaction.followup.send(
                "⚠️ 綁定過程發生錯誤，請聯絡管理員或稍後再試。",
                ephemeral=True
            )

    @app_commands.command(name="unlink", description="解除目前綁定的 UVa 帳號")
    async def unlink(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            success = await self.user_service.unlink_uva_account(
                session=session,
                discord_user_id=interaction.user.id
            )

        if success:
            role_result = await self._sync_linked_role(interaction, linked=False)
            await interaction.followup.send(
                f"✅ 已成功解除目前 Discord 帳號的 UVa 帳號綁定。\n{role_result}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ 你目前尚未綁定任何 UVa 帳號。",
                ephemeral=True
            )

    @app_commands.command(name="profile", description="查看個人或特定成員的 UVa 解題數據")
    @app_commands.describe(member="要查看的 Discord 成員（預設為自己）")
    async def profile(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        target_member = member or interaction.user

        async with get_db_session() as session:
            try:
                user, profile = await self.user_service.get_profile(
                    session=session,
                    discord_user_id=target_member.id
                )

                if not user or not user.uva_username:
                    pronoun = "你" if target_member.id == interaction.user.id else f"<@{target_member.id}>"
                    await interaction.followup.send(
                        f"⚠️ {pronoun} 尚未綁定 UVa Account。\n請先使用 `/link <uva_username>` 進行綁定。",
                        ephemeral=True
                    )
                    return

                if not profile:
                    await interaction.followup.send(
                        f"⚠️ 找不到 `{user.uva_username}` 的 UVa 詳細數據，可能是帳號不存在或 API 異常。",
                        ephemeral=True
                    )
                    return

                embed = discord.Embed(
                    title=f"👤 {target_member.display_name} 的 UVa 戰績",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="Discord：", value=f"<@{target_member.id}>", inline=True)
                embed.add_field(name="UVa：", value=f"`{profile.get('username') or user.uva_username}`", inline=True)
                if profile.get("name"):
                    embed.add_field(name="Name：", value=str(profile["name"]), inline=True)

                embed.add_field(name="Solved：", value=str(profile.get("solved", 0)), inline=True)
                embed.add_field(name="Submissions：", value=str(profile.get("submissions", 0)), inline=True)
                embed.add_field(name="AC Rate：", value=f"{profile.get('ac_rate', 0.0)}%", inline=True)

                if profile.get("rank"):
                    embed.add_field(name="World Rank：", value=f"#{profile['rank']}", inline=True)

                embed.set_thumbnail(url=target_member.display_avatar.url)
                embed.set_footer(text="資料來源：UVa Online Judge (uHunt API)")

                await interaction.followup.send(embed=embed)
            except (UvaTimeoutException, UvaApiException):
                await interaction.followup.send(
                    "⚠️ 暫時無法取得 UVa / uHunt 資料來源，請稍後再試。",
                    ephemeral=True
                )
            except Exception as e:
                logger.exception(f"Unexpected error displaying profile for {target_member.id}: {e}")
                await interaction.followup.send(
                    "⚠️ 取得個人資料時發生錯誤，請稍後再試。",
                    ephemeral=True
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountCog(bot))
