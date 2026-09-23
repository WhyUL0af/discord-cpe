from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import discord
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.ranking_repo import RankingRepository

MEDALS = ["🥇", "🥈", "🥉"]


def get_start_of_week() -> datetime:
    """Return Monday 00:00:00 UTC of the current week."""
    now = datetime.now(timezone.utc)
    start_of_week = now - timedelta(days=now.weekday())
    return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)


class RankingService:
    @staticmethod
    async def get_weekly_ranking_data(
        session: AsyncSession,
        limit: int = 10
    ) -> Tuple[List[Tuple[User, int]], int, int]:
        start_of_week = get_start_of_week()
        ranking = await RankingRepository.get_weekly_ranking(session, start_of_week, limit)
        total_subs, ac_subs = await RankingRepository.get_weekly_submission_stats(session, start_of_week)
        return ranking, total_subs, ac_subs

    @staticmethod
    async def get_all_time_ranking_data(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Tuple[User, int]]:
        return await RankingRepository.get_all_time_ranking(session, limit)

    @staticmethod
    def format_ranking_embed(
        ranking: List[Tuple[User, int]],
        title: str = "🏆 Weekly CPE Ranking",
        stats_footer: Optional[Tuple[int, int]] = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold(),
        )

        if not ranking:
            embed.description = "尚無成員解題紀錄。快去刷題搶下榜首吧！"
        else:
            lines = []
            for idx, (user, solved_count) in enumerate(ranking):
                medal = MEDALS[idx] if idx < len(MEDALS) else f"`{idx + 1}.`"
                mention = f"<@{user.discord_user_id}>"
                uva_text = f" ({user.uva_username})" if user.uva_username else ""
                lines.append(f"{medal} {mention}{uva_text}\n**{solved_count} AC**\n")
            embed.description = "\n".join(lines)

        if stats_footer:
            total_subs, ac_subs = stats_footer
            embed.add_field(
                name="📊 本週總計",
                value=f"Submissions：**{total_subs}**\nAccepted：**{ac_subs}**",
                inline=False,
            )

        embed.set_footer(text="統計依據：每人每題僅計入 1 次 Solved")
        return embed
