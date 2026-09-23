import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from app.database import get_db_session
from app.services.problem_service import ProblemService
from app.services.submission_service import SubmissionService
from app.bot.views.problem_view import ProblemActionView, create_problem_embed

logger = logging.getLogger(__name__)


class ProblemGroup(app_commands.Group):
    def __init__(self, problem_service: ProblemService) -> None:
        super().__init__(name="problem", description="CPE / UVa 題目指令")
        self.problem_service = problem_service

    @app_commands.command(name="random", description="隨機取得一題 CPE 題目")
    async def random(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session)
            if not problem:
                await interaction.followup.send("⚠️ 目前題庫中無可用題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemActionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="number", description="指定 UVa 題號取得題目")
    @app_commands.describe(problem_number="UVa 題號（例如 100, 10041）")
    async def number(self, interaction: discord.Interaction, problem_number: int) -> None:
        await interaction.response.defer(ephemeral=False)
        async with get_db_session() as session:
            problem = await self.problem_service.get_problem(session, problem_number)
            if not problem:
                await interaction.followup.send(
                    f"❌ 找不到題目 UVa {problem_number}，請確認題號是否正確。",
                    ephemeral=True
                )
                return

            embed = create_problem_embed(problem)
            view = ProblemActionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="easy", description="隨機取得一題 CPE 一星題（⭐）")
    async def easy(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        async with get_db_session() as session:
            problem = await self.problem_service.get_random_problem(session, difficulty="⭐")
            if not problem:
                await interaction.followup.send("⚠️ 目前找不到一星題目，請稍後再試。", ephemeral=True)
                return

            embed = create_problem_embed(problem)
            view = ProblemActionView(problem, self.problem_service)
            await interaction.followup.send(embed=embed, view=view)


class ProblemCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.problem_service = ProblemService()
        self.submission_service = SubmissionService()

        # Register problem slash command group
        self.problem_group = ProblemGroup(self.problem_service)
        self.bot.tree.add_command(self.problem_group)

    @app_commands.command(name="status", description="查看目前正在進行中的題目作答狀態")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        async with get_db_session() as session:
            active = await self.problem_service.get_active_session_by_user(
                session=session,
                discord_user_id=interaction.user.id
            )
            if not active or not active.problem:
                await interaction.followup.send("🎯 目前沒有進行中的題目。\n快使用 `/problem random` 開啟新題目吧！", ephemeral=True)
                return

            prob = active.problem
            started_str = active.started_at.strftime("%H:%M") if active.started_at else "剛才"
            embed = discord.Embed(
                title="🎯 Current Problem",
                description=f"**UVa {prob.problem_number}**\n{prob.title}",
                color=discord.Color.purple(),
            )
            embed.add_field(name="Difficulty：", value=prob.difficulty or "Unknown", inline=True)
            embed.add_field(name="Started：", value=started_str, inline=True)
            embed.add_field(name="Status：", value="Solving", inline=True)
            embed.add_field(name="Thread：", value=f"<#{active.thread_id}>", inline=False)
            embed.set_footer(text="完成作答後請至 UVa 提交，系統將自動偵測並更新結果。")

            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="solved", description="顯示目前已完成的題目清單")
    @app_commands.describe(member="要查看的成員（預設為自己）")
    async def solved(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        target = member or interaction.user

        async with get_db_session() as session:
            solved_list = await self.submission_service.get_user_solved(
                session=session,
                discord_user_id=target.id
            )

            embed = discord.Embed(
                title=f"📚 {target.display_name}'s Solved Problems",
                color=discord.Color.dark_green(),
            )

            if not solved_list:
                embed.description = "目前尚未在本平台解開任何題目。\n加油！使用 `/problem random` 開始練習！"
                embed.add_field(name="Total：", value="0 Problems", inline=False)
            else:
                lines = [f"{idx}. UVa {num} - {title}" for idx, (num, title) in enumerate(solved_list, 1)]
                # Handle large list pagination in description
                desc = "\n".join(lines[:25])
                if len(lines) > 25:
                    desc += f"\n... 等共 {len(lines)} 題"
                embed.description = desc
                embed.add_field(name="Total：", value=f"{len(solved_list)} Problems", inline=False)

            embed.set_thumbnail(url=target.display_avatar.url)
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProblemCog(bot))
