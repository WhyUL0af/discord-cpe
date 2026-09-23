import pytest
from app.services.guild_service import GuildService


@pytest.mark.asyncio
async def test_guild_configure_channels(async_db_session):
    guild_id = 999888777
    settings = await GuildService.configure_channels(
        session=async_db_session,
        guild_id=guild_id,
        daily_channel_id=111,
        practice_channel_id=222,
        ranking_channel_id=333,
        discussion_channel_id=444,
        archive_thread_on_solve=True,
    )

    assert settings.guild_id == guild_id
    assert settings.daily_channel_id == 111
    assert settings.practice_channel_id == 222
    assert settings.ranking_channel_id == 333
    assert settings.discussion_channel_id == 444
    assert settings.archive_thread_on_solve is True

    # Test retrieval
    fetched = await GuildService.get_settings(async_db_session, guild_id)
    assert fetched.guild_id == guild_id
    assert fetched.daily_channel_id == 111
