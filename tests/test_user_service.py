import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.user_service import UserService
from app.providers.uva_provider import UvaProvider, UvaUserNotFoundException
from app.models.user import User


@pytest.mark.asyncio
async def test_link_valid_uva_account(async_db_session):
    mock_provider = MagicMock(spec=UvaProvider)
    mock_provider.get_user_id = AsyncMock(return_value=339)
    mock_provider.get_user_profile = AsyncMock(return_value={
        "user_id": 339,
        "username": "felix_halim",
        "name": "Felix Halim",
        "rank": 4,
        "solved": 4875,
        "submissions": 13268,
        "ac_rate": 36.7,
    })

    service = UserService(uva_provider=mock_provider)
    user, profile = await service.link_uva_account(
        session=async_db_session,
        discord_user_id=123456789,
        uva_username="felix_halim",
        discord_username="felix_discord",
    )

    assert user.discord_user_id == 123456789
    assert user.uva_username == "felix_halim"
    assert user.uva_user_id == 339
    assert profile["solved"] == 4875


@pytest.mark.asyncio
async def test_link_invalid_uva_account(async_db_session):
    mock_provider = MagicMock(spec=UvaProvider)
    mock_provider.get_user_id = AsyncMock(return_value=None)

    service = UserService(uva_provider=mock_provider)
    with pytest.raises(UvaUserNotFoundException):
        await service.link_uva_account(
            session=async_db_session,
            discord_user_id=123456789,
            uva_username="unknown_user_12345",
            discord_username="test_discord",
        )


@pytest.mark.asyncio
async def test_unlink_uva_account(async_db_session):
    mock_provider = MagicMock(spec=UvaProvider)
    mock_provider.get_user_id = AsyncMock(return_value=339)
    mock_provider.get_user_profile = AsyncMock(return_value={"solved": 10})

    service = UserService(uva_provider=mock_provider)
    await service.link_uva_account(
        session=async_db_session,
        discord_user_id=987654321,
        uva_username="felix_halim",
    )

    unlinked = await service.unlink_uva_account(
        session=async_db_session,
        discord_user_id=987654321,
    )
    assert unlinked is True

    user, profile = await service.get_profile(
        session=async_db_session,
        discord_user_id=987654321,
    )
    assert user.uva_username is None
    assert profile is None
