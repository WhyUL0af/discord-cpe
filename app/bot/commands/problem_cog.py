import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.repositories.submission_repo import SubmissionRepository
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService
from app.bot.views.problem_view import (
    CurrentProblemView,
    ProblemSelectionView,
    create_current_problem_embed,
    create_problem_embed,
)

logger = logging.getLogger(__name__)


class CpeGroup(app_commands.Group):
    """Slash command group for /cpe commands (all ephemeral)."""

    def __init__(
        self,
        problem_service: ProblemService,
        submission_service: SubmissionService,
    ) -> None:
        super().__init__(name="cpe", description="CPE 刷題個人指令")
        self.problem_service = problem_service
        self.submission_service = submission_service

    @app_commands.command(name="random", description="隨機取得一題 CPE 題目")
    async def random(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session)
            if not problem:
                await interaction.followup.send("⚠️ 目前題庫中無可用題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="random")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="easy", description="隨機取得一題 CPE 一星題（⭐）")
    async def easy(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session, difficulty="⭐")
            if not problem:
                await interaction.followup.send("⚠️ 目前找不到一星題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="easy")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="problem", description="指定 UVa 題號取得題目")
    @app_commands.describe(problem_number="UVa 題號（例如 100, 10041）")
    async def problem(self, interaction: discord.Interaction, problem_number: int) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_problem(session, problem_number)
            if not problem:
                await interaction.followup.send(
                    f"❌ 找不到題目 UVa {problem_number}，請確認題號是否正確。",
                    ephemeral=True,
                )
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="current", description="查看目前正在進行中的題目作答狀態與提交紀錄")
    async def current(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session=session,
                discord_user_id=interaction.user.id,
            )
            if not active or not active.problem:
                await interaction.followup.send(
                    "🎯 目前沒有進行中的題目。\n快使用 `/cpe random` 或點選刷題中心按鈕開啟題目吧！",
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

    @app_commands.command(name="solved", description="顯示已完成的題目清單")
    @app_commands.describe(member="要查看的成員（預設為自己）")
    async def solved(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user

        async with get_db_session() as session:
            solved_list = await self.submission_service.get_user_solved(
                session=session,
                discord_user_id=target.id,
            )

            embed = discord.Embed(
                title=f"📚 {target.display_name} 的已解題目",
                color=discord.Color.dark_green(),
            )

            if not solved_list:
                embed.description = "目前尚未解開任何題目。\n加油！使用 `/cpe random` 開始練習！"
                embed.add_field(name="已解總數", value="0 題", inline=False)
            else:
                lines = [f"{idx}. UVa {num} - {title}" for idx, (num, title) in enumerate(solved_list, 1)]
                desc = "\n".join(lines[:25])
                if len(lines) > 25:
                    desc += f"\n... 等共 {len(lines)} 題"
                embed.description = desc
                embed.add_field(name="已解總數", value=f"{len(solved_list)} 題", inline=False)

            embed.set_thumbnail(url=target.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)


class LegacyProblemGroup(app_commands.Group):
    """Backward-compatible group for /problem commands (all ephemeral)."""

    def __init__(self, problem_service: ProblemService) -> None:
        super().__init__(name="problem", description="CPE / UVa 題目指令 (相容模式)")
        self.problem_service = problem_service

    @app_commands.command(name="random", description="隨機取得一題 CPE 題目")
    async def random(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session)
            if not problem:
                await interaction.followup.send("⚠️ 目前題庫中無可用題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="random")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="number", description="指定 UVa 題號取得題目")
    @app_commands.describe(problem_number="UVa 題號（例如 100, 10041）")
    async def number(self, interaction: discord.Interaction, problem_number: int) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_problem(session, problem_number)
            if not problem:
                await interaction.followup.send(
                    f"❌ 找不到題目 UVa {problem_number}，請確認題號是否正確。",
                    ephemeral=True,
                )
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="easy", description="隨機取得一題 CPE 一星題（⭐）")
    async def easy(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session, difficulty="⭐")
            if not problem:
                await interaction.followup.send("⚠️ 目前找不到一星題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemSelectionView(problem, self.problem_service, refresh_mode="easy")
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ProblemCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.problem_service = ProblemService()
        self.submission_service = SubmissionService()

        # Register primary /cpe command group
        self.cpe_group = CpeGroup(self.problem_service, self.submission_service)
        self.bot.tree.add_command(self.cpe_group)

        # Register backward-compatible /problem command group
        self.problem_group = LegacyProblemGroup(self.problem_service)
        self.bot.tree.add_command(self.problem_group)

    @app_commands.command(name="status", description="查看目前正在進行中的題目作答狀態")
    async def status(self, interaction: discord.Interaction) -> None:
        """Alias to /cpe current."""
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session=session,
                discord_user_id=interaction.user.id,
            )
            if not active or not active.problem:
                await interaction.followup.send(
                    "🎯 目前沒有進行中的題目。\n快使用 `/cpe random` 開啟新題目吧！",
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

    @app_commands.command(name="solved", description="顯示目前已完成的題目清單")
    @app_commands.describe(member="要查看的成員（預設為自己）")
    async def solved(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Alias to /cpe solved."""
        await interaction.response.defer(ephemeral=True)
        target = member or interaction.user

        async with get_db_session() as session:
            solved_list = await self.submission_service.get_user_solved(
                session=session,
                discord_user_id=target.id,
            )

            embed = discord.Embed(
                title=f"📚 {target.display_name} 的已解題目",
                color=discord.Color.dark_green(),
            )

            if not solved_list:
                embed.description = "目前尚未解開任何題目。\n加油！使用 `/cpe random` 開始練習！"
                embed.add_field(name="已解總數", value="0 題", inline=False)
            else:
                lines = [f"{idx}. UVa {num} - {title}" for idx, (num, title) in enumerate(solved_list, 1)]
                desc = "\n".join(lines[:25])
                if len(lines) > 25:
                    desc += f"\n... 等共 {len(lines)} 題"
                embed.description = desc
                embed.add_field(name="已解總數", value=f"{len(solved_list)} 題", inline=False)

            embed.set_thumbnail(url=target.display_avatar.url)
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProblemCog(bot))
