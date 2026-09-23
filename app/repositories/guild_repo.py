from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guild import GuildSettings


class GuildRepository:
    @staticmethod
    async def get_by_id(session: AsyncSession, guild_id: int) -> Optional[GuildSettings]:
        stmt = select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(session: AsyncSession, guild_id: int) -> GuildSettings:
        settings = await GuildRepository.get_by_id(session, guild_id)
        if not settings:
            settings = GuildSettings(guild_id=guild_id)
            session.add(settings)
            await session.flush()
        return settings

    @staticmethod
    async def update_channels(
        session: AsyncSession,
        guild_id: int,
        daily_channel_id: Optional[int] = None,
        practice_channel_id: Optional[int] = None,
        ranking_channel_id: Optional[int] = None,
        discussion_channel_id: Optional[int] = None,
        archive_thread_on_solve: Optional[bool] = None,
    ) -> GuildSettings:
        settings = await GuildRepository.get_or_create(session, guild_id)
        if daily_channel_id is not None:
            settings.daily_channel_id = daily_channel_id
        if practice_channel_id is not None:
            settings.practice_channel_id = practice_channel_id
        if ranking_channel_id is not None:
            settings.ranking_channel_id = ranking_channel_id
        if discussion_channel_id is not None:
            settings.discussion_channel_id = discussion_channel_id
        if archive_thread_on_solve is not None:
            settings.archive_thread_on_solve = archive_thread_on_solve
        await session.flush()
        return settings

    @staticmethod
    async def update_ranking_message_id(
        session: AsyncSession,
        guild_id: int,
        ranking_message_id: int
    ) -> GuildSettings:
        settings = await GuildRepository.get_or_create(session, guild_id)
        settings.ranking_message_id = ranking_message_id
        await session.flush()
        return settings

    @staticmethod
    async def update_practice_message_id(
        session: AsyncSession,
        guild_id: int,
        practice_message_id: int
    ) -> GuildSettings:
        settings = await GuildRepository.get_or_create(session, guild_id)
        settings.practice_message_id = practice_message_id
        await session.flush()
        return settings
