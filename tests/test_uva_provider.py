import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.providers.uva_provider import (
    UvaProvider,
    UvaApiException,
    UvaUserNotFoundException,
    UvaTimeoutException,
)


@pytest.mark.asyncio
async def test_get_user_id_success():
    provider = UvaProvider()
    with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = 339
        uid = await provider.get_user_id("felix_halim")
        assert uid == 339
        mock_get.assert_called_once_with("uname2uid/felix_halim")


@pytest.mark.asyncio
async def test_get_user_id_not_found():
    provider = UvaProvider()
    with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = 0
        uid = await provider.get_user_id("non_existent_user_xyz")
        assert uid is None


@pytest.mark.asyncio
async def test_get_user_profile_success():
    provider = UvaProvider()
    mock_data = [
        {
            "rank": 4,
            "old": 0,
            "userid": 339,
            "name": "Felix Halim",
            "username": "felix_halim",
            "ac": 4875,
            "nos": 13268,
            "activity": [0, 0, 0, 3354, 3354],
        }
    ]
    with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        profile = await provider.get_user_profile(339)
        assert profile["user_id"] == 339
        assert profile["username"] == "felix_halim"
        assert profile["solved"] == 4875
        assert profile["submissions"] == 13268
        assert profile["ac_rate"] == 36.7
        assert profile["rank"] == 4


@pytest.mark.asyncio
async def test_get_user_profile_empty_result():
    provider = UvaProvider()
    with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        with pytest.raises(UvaUserNotFoundException):
            await provider.get_user_profile(99999999)
