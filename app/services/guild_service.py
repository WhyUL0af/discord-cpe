import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guild import GuildSettings
from app.repositories.guild_repo import GuildRepository

logger = logging.getLogger(__name__)


class GuildService:
    @staticmethod
    async def get_settings(session: AsyncSession, guild_id: int) -> GuildSettings:
        return await GuildRepository.get_or_create(session, guild_id)

    @staticmethod
    async def configure_channels(
        session: AsyncSession,
        guild_id: int,
        daily_channel_id: Optional[int] = None,
        practice_channel_id: Optional[int] = None,
        ranking_channel_id: Optional[int] = None,
        discussion_channel_id: Optional[int] = None,
        archive_thread_on_solve: Optional[bool] = None,
    ) -> GuildSettings:
        settings = await GuildRepository.update_channels(
            session=session,
            guild_id=guild_id,
            daily_channel_id=daily_channel_id,
            practice_channel_id=practice_channel_id,
            ranking_channel_id=ranking_channel_id,
            discussion_channel_id=discussion_channel_id,
            archive_thread_on_solve=archive_thread_on_solve,
        )
        logger.info(f"Updated configuration for Guild {guild_id}")
        return settings

    @staticmethod
    async def set_ranking_message(
        session: AsyncSession,
        guild_id: int,
        message_id: int,
    ) -> GuildSettings:
        return await GuildRepository.update_ranking_message_id(session, guild_id, message_id)
