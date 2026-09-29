import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.services.mock_exam_service import DURATION_MINUTES, LEVEL_NAMES, MockExamService
from app.bot.views.submission_results_view import SubmissionResultsView

logger = logging.getLogger(__name__)


class MockExamCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = MockExamService()

    @app_commands.command(name="mock_exam", description="在目前頻道發送 CPE 風格 7 題模擬考通知")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def mock_exam(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.followup.send("請在模擬考文字頻道使用此指令。", ephemeral=True)
            return
        try:
            async with get_db_session() as session:
                selected = await self.service.create_set(session)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            logger.exception("Could not prepare mock exam notification")
            await interaction.followup.send("暫時無法取得題組，請稍後重試。", ephemeral=True)
            return

        start = datetime.now(timezone.utc)
        end = start + timedelta(minutes=DURATION_MINUTES)
        embed = discord.Embed(
            title="🏁 CPE 風格模擬考｜7 題・3 小時",
            description=(f"開始：<t:{int(start.timestamp())}:F>\n"
                         f"建議完成時間：<t:{int(end.timestamp())}:F>\n\n"
                         "點擊題目名稱閱讀題目，自行至 UVa Online Judge 提交。\n"
                         "先使用 `/link` 綁定 UVa 帳號。提交後點「🔄 查看提交結果」，只有自己能看到回覆。"),
            color=discord.Color.purple(),
        )
        for index, (candidate, problem) in enumerate(selected, 1):
            embed.add_field(
                name=f"第 {index} 題・{LEVEL_NAMES[candidate.level]}（本站評估）",
                value=f"[UVa {problem.problem_number} — {problem.title}]({problem.external_url})",
                inline=False,
            )
        embed.set_footer(text="本站組題，非官方 CPE 試卷。排行榜僅計 uHunt AC，同一題僅計一次；3 小時為練習時間提示。")
        view = SubmissionResultsView()
        view.add_item(discord.ui.Button(label="🌐 前往 UVa 提交", url="https://onlinejudge.org/"))
        try:
            await interaction.channel.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            await interaction.followup.send("通知發送失敗，請確認 Bot 的頻道權限後重試。", ephemeral=True)
            return
        await interaction.followup.send("已發送 7 題模擬考通知。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MockExamCog(bot))
