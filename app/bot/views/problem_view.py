import asyncio
import logging
from datetime import date, datetime, timezone
from typing import List, Optional
import discord

from app.database import get_db_session
from app.models.problem import Problem
from app.models.session import ActiveProblemSession
from app.models.submission import Submission
from app.repositories.daily_repo import DailyRepository
from app.repositories.submission_repo import SubmissionRepository
from app.services.daily_service import DailyService
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService
from app.bot.views.submission_results_view import SubmissionResultsButton

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
    embed.set_footer(text="自行至 UVa 提交；先用 /link 綁定帳號，Bot 會自動追蹤 uHunt 評測結果。")
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
        title="💻 CPE 自主練習",
        description=("點下方按鈕取得題目，題目回覆只有你自己看得到。\n\n"
                     "先用 `/link` 綁定 UVa 帳號，再閱讀題目並自行到 UVa Online Judge 提交。\n"
                     "點「🔄 查看提交結果」取得私人回覆；排行榜自動更新，不會發送私訊。"),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="CPE Discord Bot ｜ 提升程式能力，輕鬆應考 CPE")
    return embed


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


async def start_problem_for_user(
    interaction: discord.Interaction,
    problem: Optional[Problem] = None,
    problem_number: Optional[int] = None,
    problem_service: Optional[ProblemService] = None,
    is_daily: bool = False,
) -> None:
    """Resolve legacy buttons and explain the external submission workflow."""
    is_done = False
    try:
        res = interaction.response.is_done()
        if asyncio.iscoroutine(res):
            is_done = await res
        else:
            is_done = bool(res)
    except Exception:
        is_done = False

    if not is_done:
        await interaction.response.defer(ephemeral=True)

    problem_service = problem_service or ProblemService()

    # 1. Resolve problem if not directly provided
    target_problem = problem
    if target_problem is None and problem_number is not None:
        async with get_db_session() as session:
            target_problem = await problem_service.get_problem(session, problem_number)

    if target_problem is None and is_daily:
        async with get_db_session() as session:
            daily = None
            if interaction.message:
                daily = await DailyRepository.get_by_message_id(session, interaction.message.id)
            if not daily and interaction.guild_id:
                daily = await DailyRepository.get_by_guild_and_date(session, interaction.guild_id, date.today())
            if not daily:
                daily = await DailyRepository.get_any_by_date(session, date.today())
            if daily and daily.problem:
                target_problem = daily.problem

    if target_problem is None:
        await interaction.followup.send("⚠️ 找不到題目資料，請稍後再試。", ephemeral=True)
        return

    # Legacy buttons now provide instructions without creating single-problem sessions.
    await interaction.followup.send(
        f"請自行至 UVa Online Judge 提交 **UVa {target_problem.problem_number}**。\n"
        "使用 `/link` 綁定 UVa 帳號後，Bot 會自動追蹤題庫中的提交結果；可同時練習多題。",
        ephemeral=True,
    )
    return


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

        self.remove_item(self.start_button)
        self.add_item(discord.ui.Button(label="🌐 前往 UVa 提交", url="https://onlinejudge.org/"))
        self.add_item(SubmissionResultsButton())

        if problem.external_url:
            self.add_item(
                discord.ui.Button(
                    label="📖 查看題目",
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
        await start_problem_for_user(
            interaction=interaction,
            problem=self.problem,
            problem_service=self.problem_service,
        )

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


# Backward-compatibility aliases
ProblemActionView = ProblemSelectionView
ProblemCardView = ProblemSelectionView


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
        self.remove_item(self.current_button)
        self.add_item(SubmissionResultsButton())

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
        label="⭐ 基礎題",
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
        label="🔎 指定題號",
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
        label="✅ 已解題目",
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


class DailyProblemView(discord.ui.View):
    """Persistent view attached to the Daily Problem message."""

    def __init__(
        self,
        problem: Optional[Problem] = None,
        problem_service: Optional[ProblemService] = None,
        daily_service: Optional[DailyService] = None,
    ) -> None:
        super().__init__(timeout=None)
        self.problem = problem
        self.problem_service = problem_service or ProblemService()
        self.daily_service = daily_service or DailyService()
        self.add_item(SubmissionResultsButton())

        if problem:
            self.remove_item(self.start_button)
            self.add_item(discord.ui.Button(label="🌐 前往 UVa 提交", url="https://onlinejudge.org/"))

        if problem and problem.external_url:
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
        button: discord.ui.Button,
    ) -> None:
        await start_problem_for_user(
            interaction=interaction,
            problem=self.problem,
            problem_service=self.problem_service,
            is_daily=True,
        )

    @discord.ui.button(
        label="📊 查看統計",
        style=discord.ButtonStyle.secondary,
        custom_id="cpe_daily_stats_button",
    )
    async def stats_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = self.problem
            daily_date = date.today()
            if not problem:
                daily = None
                if interaction.message:
                    daily = await DailyRepository.get_by_message_id(session, interaction.message.id)
                if not daily and interaction.guild_id:
                    daily = await DailyRepository.get_by_guild_and_date(session, interaction.guild_id, date.today())
                if not daily:
                    daily = await DailyRepository.get_any_by_date(session, date.today())
                if daily:
                    problem = daily.problem
                    daily_date = daily.date

            if not problem:
                await interaction.followup.send("⚠️ 找不到今日題目的統計資料。", ephemeral=True)
                return

            solved_today = await self.daily_service.count_solved_today(
                session=session,
                problem_id=problem.id,
                target_date=daily_date,
            )
            embed = discord.Embed(
                title=f"📊 今日解題統計：UVa {problem.problem_number}",
                description=f"今日已有 **{solved_today}** 位成員成功解答 (AC)！",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
