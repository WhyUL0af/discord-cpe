import logging
from datetime import datetime, timezone
from typing import List, Optional
import discord

from app.database import get_db_session
from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.submission import Submission
from app.repositories.submission_repo import SubmissionRepository
from app.services.problem_service import (
    ActiveSessionConflictException,
    ProblemService,
    UserNotLinkedException,
)
from app.services.submission_service import SubmissionService

logger = logging.getLogger(__name__)

VERDICT_MAP_DISPLAY = {
    "Accepted": ("✅", "Accepted"),
    "Wrong Answer": ("❌", "Wrong Answer"),
    "Time Limit Exceeded": ("⏱", "Time Limit Exceeded"),
    "Compilation Error": ("🛠", "Compilation Error"),
    "Runtime Error": ("💥", "Runtime Error"),
    "Memory Limit Exceeded": ("💾", "Memory Limit Exceeded"),
    "Output Limit Exceeded": ("📄", "Output Limit Exceeded"),
    "Presentation Error": ("📝", "Presentation Error"),
    "In queue": ("⏳", "In Queue"),
}


def create_problem_embed(problem: Problem) -> discord.Embed:
    diff = problem.difficulty or "⭐"
    embed = discord.Embed(
        title="🎲 你的題目",
        description=f"**UVa {problem.problem_number}**\n{problem.title}\n\n難度：{diff}",
        color=discord.Color.blue(),
    )
    if problem.time_limit:
        embed.add_field(name="Time Limit", value=f"{problem.time_limit} ms", inline=True)
    if problem.source:
        embed.add_field(name="Source", value=problem.source, inline=True)
    embed.set_footer(text="點擊「🌐 查看題目」開啟題目，點擊「▶ 開始作答」記錄作答。")
    return embed


def format_elapsed_time(started_at: datetime) -> str:
    elapsed_seconds = max(0, int((datetime.now(timezone.utc) - started_at).total_seconds()))
    mins = elapsed_seconds // 60
    hrs = mins // 60
    if hrs > 0:
        return f"{hrs} 小時 {mins % 60} 分鐘"
    elif mins > 0:
        return f"{mins} 分鐘"
    else:
        return f"{elapsed_seconds} 秒"


def create_current_problem_embed(
    problem: Problem,
    active_session: ActiveProblemSession,
    attempts: int,
    recent_submissions: List[Submission],
) -> discord.Embed:
    started_str = (
        active_session.started_at.strftime("%H:%M")
        if active_session.started_at
        else "剛才"
    )
    elapsed_str = (
        format_elapsed_time(active_session.started_at)
        if active_session.started_at
        else "0 分鐘"
    )

    embed = discord.Embed(
        title="📌 目前作答",
        description=f"**UVa {problem.problem_number}**\n{problem.title}",
        color=discord.Color.purple(),
    )
    embed.add_field(name="難度", value=problem.difficulty or "⭐", inline=True)
    embed.add_field(name="開始時間", value=started_str, inline=True)
    embed.add_field(name="作答時間", value=elapsed_str, inline=True)
    embed.add_field(name="Attempts", value=str(attempts), inline=True)

    if recent_submissions:
        sub_lines = []
        for s in recent_submissions:
            time_str = s.submitted_at.strftime("%H:%M") if s.submitted_at else ""
            emoji, verdict_name = VERDICT_MAP_DISPLAY.get(s.verdict, ("❓", s.verdict))
            sub_lines.append(f"{emoji} {verdict_name} — {time_str}")
        sub_text = "\n".join(sub_lines)
    else:
        sub_text = "尚未有提交紀錄"

    embed.add_field(name="最近提交", value=sub_text, inline=False)
    embed.set_footer(text="在 UVa 提交後點擊「重新整理」更新狀態，或點擊「結束作答」。")
    return embed


def create_practice_center_embed() -> discord.Embed:
    embed = discord.Embed(
        title="💻 CPE 刷題中心",
        description="在這裡進行 CPE 題目練習。\n你的題目、作答紀錄與提交結果只有你自己能看到。",
        color=discord.Color.blue(),
    )
    embed.set_footer(text="CPE Discord Bot ｜ 提升程式能力，輕鬆應考 CPE")
    return embed


class ProblemSelectionView(discord.ui.View):
    """View returned for a selected problem with options to start solving, view external link, or reroll."""

    def __init__(
        self,
        problem: Problem,
        problem_service: Optional[ProblemService] = None,
        refresh_mode: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.problem = problem
        self.problem_service = problem_service or ProblemService()
        self.refresh_mode = refresh_mode

        if problem.external_url:
            self.add_item(
                discord.ui.Button(
                    label="🌐 查看題目",
                    url=problem.external_url,
                    style=discord.ButtonStyle.link,
                )
            )

    @discord.ui.button(
        label="▶ 開始作答",
        style=discord.ButtonStyle.success,
        custom_id="cpe_select_start",
    )
    async def start_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            try:
                existing_session, is_new = await self.problem_service.start_problem_session(
                    session=session,
                    discord_user_id=interaction.user.id,
                    problem_number=self.problem.problem_number,
                    discord_username=interaction.user.name,
                )

                if is_new:
                    await interaction.followup.send(
                        f"✅ 已開始作答 **UVa {self.problem.problem_number} - {self.problem.title}**！\n"
                        f"請前往 UVa 提交程式碼。系統將透過 **Discord 私訊 (DM)** 即時通知評測結果。\n"
                        f"💡 **提示**：請確保你的 Discord 隱私設定允許接收私訊 (DM)。",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        f"ℹ️ 你已經在作答 **UVa {self.problem.problem_number}**！\n"
                        f"系統持續追蹤提交中，可使用 `/status` 或點選「📌 目前作答」查看進度。",
                        ephemeral=True,
                    )
            except ActiveSessionConflictException as conflict:
                active_prob = conflict.active_session.problem
                prob_title = active_prob.title if active_prob else ""
                prob_num = active_prob.problem_number if active_prob else conflict.active_session.problem_id
                embed = discord.Embed(
                    title="⚠️ 你目前正在作答其他題目",
                    description=(
                        f"你目前正在作答：\n\n"
                        f"**UVa {prob_num} - {prob_title}**\n\n"
                        f"每位使用者同時只能有一題進行中的題目。\n"
                        f"請先完成或結束目前的作答，才能開始新題目！"
                    ),
                    color=discord.Color.orange(),
                )
                view = ActiveConflictView(conflict.active_session, self.problem_service)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            except UserNotLinkedException:
                await interaction.followup.send(
                    "⚠️ 尚未綁定 UVa Account\n請先使用 `/link <uva_username>` 完成帳號綁定。",
                    ephemeral=True,
                )
            except Exception as e:
                logger.exception(f"Error starting problem session for {interaction.user.id}: {e}")
                await interaction.followup.send("⚠️ 啟動作答時發生錯誤，請稍後再試。", ephemeral=True)

    @discord.ui.button(
        label="🔄 換一題",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_select_reroll",
    )
    async def reroll_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not self.refresh_mode:
            await interaction.response.send_message("指定題號無法換一題，請使用「🔎 指定題目」輸入其他題號。", ephemeral=True)
            return

        await interaction.response.defer()
        async with get_db_session() as session:
            diff = "⭐" if self.refresh_mode == "easy" else None
            new_prob = await self.problem_service.get_random_problem(session, difficulty=diff)
            if not new_prob:
                await interaction.followup.send("⚠️ 暫無其他題目可更換。", ephemeral=True)
                return

            new_view = ProblemSelectionView(new_prob, self.problem_service, refresh_mode=self.refresh_mode)
            embed = create_problem_embed(new_prob)
            await interaction.edit_original_response(embed=embed, view=new_view)


# Backward-compatibility alias
ProblemActionView = ProblemSelectionView


class ActiveConflictView(discord.ui.View):
    """View rendered when user attempts to start a problem while already solving another."""

    def __init__(
        self,
        active_session: ActiveProblemSession,
        problem_service: Optional[ProblemService] = None,
        submission_service: Optional[SubmissionService] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.active_session = active_session
        self.problem_service = problem_service or ProblemService()
        self.submission_service = submission_service or SubmissionService()

    @discord.ui.button(
        label="📌 查看目前作答",
        style=discord.ButtonStyle.primary,
        custom_id="cpe_conflict_view",
    )
    async def view_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session, interaction.user.id
            )
            if not active or not active.problem:
                await interaction.followup.send("🎯 目前沒有進行中的題目。", ephemeral=True)
                return

            prob = active.problem
            attempts = await SubmissionRepository.count_attempts(session, active.user_id, prob.id)
            recent_subs = await SubmissionRepository.get_recent_submissions_for_problem(
                session, active.user_id, prob.id, limit=5
            )
            embed = create_current_problem_embed(prob, active, attempts, recent_subs)
            view = CurrentProblemView(prob, self.problem_service, self.submission_service)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="⏹ 結束目前作答",
        style=discord.ButtonStyle.danger,
        custom_id="cpe_conflict_close",
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            closed = await self.problem_service.close_problem_session(
                session, interaction.user.id
            )
            if closed:
                await interaction.followup.send(
                    "⏹ 已成功結束目前作答！你現在可以重新點擊「▶ 開始作答」開始新題目。",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("🎯 目前沒有進行中的作答可結束。", ephemeral=True)


class CurrentProblemView(discord.ui.View):
    """View attached to /status or [📌 目前作答] embed."""

    def __init__(
        self,
        problem: Problem,
        problem_service: Optional[ProblemService] = None,
        submission_service: Optional[SubmissionService] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.problem = problem
        self.problem_service = problem_service or ProblemService()
        self.submission_service = submission_service or SubmissionService()

        if problem.external_url:
            self.add_item(
                discord.ui.Button(
                    label="🌐 查看題目",
                    url=problem.external_url,
                    style=discord.ButtonStyle.link,
                )
            )

    @discord.ui.button(
        label="🔄 重新整理",
        style=discord.ButtonStyle.primary,
        custom_id="cpe_current_refresh",
    )
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session, interaction.user.id
            )
            if not active or not active.problem:
                await interaction.edit_original_response(
                    content="🎯 目前沒有進行中的題目。",
                    embed=None,
                    view=None,
                )
                return

            prob = active.problem
            attempts = await SubmissionRepository.count_attempts(
                session, active.user_id, prob.id
            )
            recent_subs = await SubmissionRepository.get_recent_submissions_for_problem(
                session, active.user_id, prob.id, limit=5
            )
            embed = create_current_problem_embed(prob, active, attempts, recent_subs)
            await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(
        label="⏹ 結束作答",
        style=discord.ButtonStyle.danger,
        custom_id="cpe_current_close",
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        async with get_db_session() as session:
            closed = await self.problem_service.close_problem_session(
                session, interaction.user.id
            )
            if closed:
                embed = discord.Embed(
                    title="⏹ 已結束作答",
                    description=f"你已結束 **UVa {self.problem.problem_number} - {self.problem.title}** 的作答流程。",
                    color=discord.Color.light_grey(),
                )
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                await interaction.edit_original_response(
                    content="🎯 目前沒有進行中的題目可結束。",
                    embed=None,
                    view=None,
                )


class ProblemSearchModal(discord.ui.Modal, title="🔎 指定題目"):
    problem_input = discord.ui.TextInput(
        label="UVa 題號",
        placeholder="例如: 100, 10041, 10107",
        min_length=1,
        max_length=10,
        required=True,
    )

    def __init__(self, problem_service: Optional[ProblemService] = None) -> None:
        super().__init__()
        self.problem_service = problem_service or ProblemService()

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_val = self.problem_input.value.strip()
        if not raw_val.isdigit():
            await interaction.response.send_message("❌ 請輸入有效的數字題號（例如 100）。", ephemeral=True)
            return

        problem_number = int(raw_val)
        await interaction.response.defer(ephemeral=True)

        async with get_db_session() as session:
            problem = await self.problem_service.get_problem(session, problem_number)
            if not problem:
                await interaction.followup.send(
                    f"找不到 UVa {problem_number}，\n請確認題號是否正確。",
                    ephemeral=True,
                )
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class PracticeCenterView(discord.ui.View):
    """Persistent view attached to the fixed CPE 刷題中心 message."""

    def __init__(
        self,
        problem_service: Optional[ProblemService] = None,
        submission_service: Optional[SubmissionService] = None,
    ) -> None:
        super().__init__(timeout=None)
        self.problem_service = problem_service or ProblemService()
        self.submission_service = submission_service or SubmissionService()

    @discord.ui.button(
        label="🎲 隨機一題",
        style=discord.ButtonStyle.primary,
        custom_id="cpe_practice_random",
    )
    async def random_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session)
            if not problem:
                await interaction.followup.send("⚠️ 目前題庫中無可用題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="random")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="⭐ 一星題",
        style=discord.ButtonStyle.success,
        custom_id="cpe_practice_easy",
    )
    async def easy_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session, difficulty="⭐")
            if not problem:
                await interaction.followup.send("⚠️ 目前找不到一星題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="easy")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="🔎 指定題目",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_practice_search",
    )
    async def search_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(ProblemSearchModal(self.problem_service))

    @discord.ui.button(
        label="📌 目前作答",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_practice_current",
    )
    async def current_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session, interaction.user.id
            )
            if not active or not active.problem:
                await interaction.followup.send(
                    "🎯 目前沒有進行中的題目。\n快點選「🎲 隨機一題」或「⭐ 一星題」開啟練習吧！",
                    ephemeral=True,
                )
                return

            prob = active.problem
            attempts = await SubmissionRepository.count_attempts(session, active.user_id, prob.id)
            recent_subs = await SubmissionRepository.get_recent_submissions_for_problem(
                session, active.user_id, prob.id, limit=5
            )
            embed = create_current_problem_embed(prob, active, attempts, recent_subs)
            view = CurrentProblemView(prob, self.problem_service, self.submission_service)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(
        label="✅ 已完成題目",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_practice_solved",
    )
    async def solved_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            solved_list = await self.submission_service.get_user_solved(
                session=session,
                discord_user_id=interaction.user.id,
            )

            embed = discord.Embed(
                title="✅ 我的 CPE 解題紀錄",
                color=discord.Color.dark_green(),
            )

            if not solved_list:
                embed.description = "已完成：0 題\n\n目前尚未解開任何題目。\n點擊「🎲 隨機一題」開始練習！"
            else:
                lines = [f"UVa {num} - {title}" for (num, title) in solved_list]
                desc = f"已完成：{len(solved_list)} 題\n\n" + "\n".join(lines[:25])
                if len(lines) > 25:
                    desc += f"\n... 等共 {len(lines)} 題"
                embed.description = desc

            await interaction.followup.send(embed=embed, ephemeral=True)
