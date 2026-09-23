import logging
import discord
from discord import app_commands
from discord.ext import commands

from app.providers.uva_provider import (
    UvaApiException,
    UvaUserNotFoundException,
    UvaTimeoutException,
)

logger = logging.getLogger(__name__)


class GlobalErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        # Unwrap CommandInvokeError
        if isinstance(error, app_commands.CommandInvokeError):
            original = error.original
        else:
            original = error

        if isinstance(original, UvaUserNotFoundException):
            msg = f"❌ {str(original)}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        if isinstance(original, UvaTimeoutException):
            msg = "⚠️ UVa / uHunt API 連線逾時，請稍後再試。"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        if isinstance(original, UvaApiException):
            msg = "⚠️ 暫時無法取得 UVa 資料來源，請稍後再試。"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        if isinstance(original, app_commands.MissingPermissions):
            msg = "🚫 你沒有執行此指令所需的權限（需要管理員權限）。"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        logger.exception(f"Unhandled app command error in {interaction.command}: {error}")
        msg = "⚠️ 執行指令時發生未預期的錯誤，請稍後再試。"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GlobalErrorHandler(bot))
