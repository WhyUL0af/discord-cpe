import logging
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.providers.uva_provider import (
    UvaProvider,
    UvaUserNotFoundException,
    UvaApiException,
)

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, uva_provider: Optional[UvaProvider] = None) -> None:
        self.uva_provider = uva_provider or UvaProvider()

    async def link_uva_account(
        self,
        session: AsyncSession,
        discord_user_id: int,
        uva_username: str,
        discord_username: Optional[str] = None,
    ) -> Tuple[User, Dict[str, Any]]:
        """Verify UVa username on uHunt and link to Discord user."""
        cleaned_username = uva_username.strip()
        uid = await self.uva_provider.get_user_id(cleaned_username)
        if not uid:
            raise UvaUserNotFoundException(f"找不到 UVa User：{cleaned_username}")

        user = await UserRepository.link_uva(
            session=session,
            discord_user_id=discord_user_id,
            uva_username=cleaned_username,
            uva_user_id=uid,
            discord_username=discord_username,
        )

        logger.info(f"User {discord_user_id} linked UVa account {cleaned_username} (UID: {uid})")

        # Fetch initial stats
        try:
            profile = await self.uva_provider.get_user_profile(uid)
        except Exception:
            profile = {"username": cleaned_username, "solved": 0, "submissions": 0, "ac_rate": 0.0}

        return user, profile

    async def unlink_uva_account(
        self,
        session: AsyncSession,
        discord_user_id: int,
    ) -> bool:
        """Unlink UVa account from Discord user."""
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user or not user.uva_username:
            return False

        old_uva = user.uva_username
        await UserRepository.unlink_uva(session, discord_user_id)
        logger.info(f"User {discord_user_id} unlinked UVa account {old_uva}")
        return True

    async def get_profile(
        self,
        session: AsyncSession,
        discord_user_id: int,
    ) -> Tuple[Optional[User], Optional[Dict[str, Any]]]:
        """Retrieve user record and uHunt statistics."""
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user or not user.uva_username:
            return user, None

        uid = user.uva_user_id
        if not uid:
            uid = await self.uva_provider.get_user_id(user.uva_username)
            if uid:
                user.uva_user_id = uid
                await session.flush()

        if not uid:
            return user, None

        profile = await self.uva_provider.get_user_profile(uid)
        return user, profile
