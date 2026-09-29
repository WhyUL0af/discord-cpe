"""Persistent result lookup; every response belongs to the clicking user."""

import logging
import re
from datetime import timezone

import discord
from sqlalchemy import select

from app.database import get_db_session
from app.models.problem import Problem
from app.models.submission import Submission
from app.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)
RESULTS_CUSTOM_ID = "cpe_view_submission_results"


def problem_numbers_from_message(message) -> list[int]:
    """Recover scope from the bot's published card, including after a restart."""
    numbers = set()
    for embed in getattr(message, "embeds", []):
        text = "\n".join([embed.title or "", embed.description or ""] +
                         [str(field.value) for field in embed.fields])
        numbers.update(int(number) for number in re.findall(r"\bUVa\s+(\d+)\b", text, re.IGNORECASE))
    return sorted(numbers)


async def show_submission_results(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    numbers = problem_numbers_from_message(interaction.message)
    try:
        async with get_db_session() as session:
            user = await UserRepository.get_by_discord_id(session, interaction.user.id)
            if not user or not user.uva_user_id:
                await interaction.followup.send("請先使用 `/link` 綁定你的 UVa 帳號。", ephemeral=True)
                return
            # Never accept another user's ID from a button, message, or command argument.
            stmt = (select(Problem.problem_number, Problem.title, Submission.verdict,
                           Submission.external_submission_id, Submission.language, Submission.submitted_at)
                    .join(Submission, Submission.problem_id == Problem.id)
                    .where(Submission.user_id == user.id, Submission.source == "uhunt",
                           Submission.external_submission_id.isnot(None))
                    .order_by(Submission.submitted_at.desc(), Submission.external_submission_id.desc()).limit(10))
            if numbers:
                stmt = stmt.where(Problem.problem_number.in_(numbers))
            rows = list((await session.execute(stmt)).all())
        embed = discord.Embed(title="🔄 我的提交結果", color=discord.Color.blue())
        if not rows:
            embed.description = "尚無已同步的提交紀錄。請確認已在 UVa 提交，稍候再點按鈕查詢。"
        else:
            embed.description = "本題最近提交" if len(numbers) == 1 else (
                "本次題組最近提交" if numbers else "最近提交（Bot 已知題庫）")
            for number, title, verdict, sid, language, submitted_at in rows:
                stamp = submitted_at.replace(tzinfo=timezone.utc) if submitted_at.tzinfo is None else submitted_at
                embed.add_field(
                    name=f"UVa {number} — {title}"[:256],
                    value=f"**{verdict}**\n提交 ID：{sid}｜{language or '語言未提供'}\n<t:{int(stamp.timestamp())}:f>",
                    inline=False,
                )
        embed.set_footer(text="只有你能看到此回覆。資料依 uHunt 背景同步更新；直接到 UVa 提交，無需開始作答。")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception:
        logger.exception("Could not retrieve private results for Discord user %s", interaction.user.id)
        await interaction.followup.send("暫時無法讀取提交結果，請稍後重試。", ephemeral=True)


class SubmissionResultsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔄 查看提交結果", style=discord.ButtonStyle.primary, custom_id=RESULTS_CUSTOM_ID)

    async def callback(self, interaction):
        await show_submission_results(interaction)


class SubmissionResultsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SubmissionResultsButton())
