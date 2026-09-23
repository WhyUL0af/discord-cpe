import logging
from typing import Optional
import discord

from app.database import get_db_session
from app.models.problem import Problem
from app.services.problem_service import ProblemService, UserNotLinkedException

logger = logging.getLogger(__name__)


def create_problem_embed(problem: Problem) -> discord.Embed:
    diff = problem.difficulty or "Unknown"
    embed = discord.Embed(
        title=f"📘 UVa {problem.problem_number}",
        description=f"**{problem.title}**",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Difficulty：", value=diff, inline=True)
    embed.add_field(name="Source：", value=problem.source or "UVa Online Judge", inline=True)
    if problem.time_limit:
        embed.add_field(name="Time Limit：", value=f"{problem.time_limit} ms", inline=True)
    embed.set_footer(text="點擊「📖 查看題目」開啟題目，點擊「💻 開始作答」建立專屬作答空間。")
    return embed


class ProblemActionView(discord.ui.View):
    def __init__(self, problem: Problem, problem_service: Optional[ProblemService] = None) -> None:
        super().__init__(timeout=None)
        self.problem = problem
        self.problem_service = problem_service or ProblemService()

        # External Link Button
        if problem.external_url:
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
        custom_id="cpe_start_problem_button",
    )
    async def start_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild or not interaction.channel:
            await interaction.followup.send("❌ 此操作僅限在 Discord 伺服器頻道中使用。", ephemeral=True)
            return

        async with get_db_session() as session:
            try:
                # First check user binding and active session without creating thread yet
                existing_session, is_new = await self.problem_service.start_problem_session(
                    session=session,
                    discord_user_id=interaction.user.id,
                    problem_number=self.problem.problem_number,
                    thread_id=0,  # placeholder if new
                    discord_username=interaction.user.name,
                )

                if not is_new:
                    # User already has active thread
                    await interaction.followup.send(
                        f"ℹ️ 你已經有進行中的作答 Thread：<#{existing_session.thread_id}>",
                        ephemeral=True,
                    )
                    return

                # Create Thread for new session
                thread_name = f"UVa {self.problem.problem_number}｜{interaction.user.name}"
                # Threads must be created in a TextChannel
                target_channel = interaction.channel
                if isinstance(target_channel, discord.Thread):
                    target_channel = target_channel.parent

                if not isinstance(target_channel, discord.TextChannel):
                    await interaction.followup.send(
                        "❌ 無法在此類型的頻道中建立 Thread。",
                        ephemeral=True,
                    )
                    return

                thread = await target_channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440,  # 24 hours
                    type=discord.ChannelType.public_thread,
                )

                # Update session with actual thread_id
                existing_session.thread_id = thread.id
                await session.flush()

                # Post initial message in thread
                thread_embed = discord.Embed(
                    title=f"📘 UVa {self.problem.problem_number}",
                    description=f"**{self.problem.title}**\n\nDifficulty：{self.problem.difficulty or 'Unknown'}\n\n請前往 UVa Online Judge 完成題目並提交程式碼。",
                    color=discord.Color.green(),
                )
                thread_embed.set_footer(text="Bot 正在追蹤你的 Submission。")

                thread_view = discord.ui.View()
                if self.problem.external_url:
                    thread_view.add_item(
                        discord.ui.Button(
                            label="📖 查看題目",
                            url=self.problem.external_url,
                            style=discord.ButtonStyle.link,
                        )
                    )

                await thread.send(
                    content=f"👋 <@{interaction.user.id}> 專屬刷題空間已建立！",
                    embed=thread_embed,
                    view=thread_view,
                )

                await interaction.followup.send(
                    f"🚀 已為你建立作答空間：<#{thread.id}>\n請前往該 Thread 開始解題！",
                    ephemeral=True,
                )

            except UserNotLinkedException:
                await interaction.followup.send(
                    "⚠️ 尚未綁定 UVa Account\n請先使用：\n`/link <uva_username>`",
                    ephemeral=True,
                )
            except Exception as e:
                logger.exception(f"Error starting problem session for {interaction.user.id}: {e}")
                await interaction.followup.send(
                    "⚠️ 建立作答空間時發生錯誤，請稍後再試。",
                    ephemeral=True,
                )
