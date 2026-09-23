from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    @staticmethod
    async def get_by_discord_id(session: AsyncSession, discord_user_id: int) -> Optional[User]:
        stmt = select(User).where(User.discord_user_id == discord_user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_uva_username(session: AsyncSession, uva_username: str) -> Optional[User]:
        stmt = select(User).where(User.uva_username.ilike(uva_username))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        discord_user_id: int,
        discord_username: Optional[str] = None
    ) -> User:
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if not user:
            user = User(
                discord_user_id=discord_user_id,
                discord_username=discord_username
            )
            session.add(user)
            await session.flush()
        elif discord_username and user.discord_username != discord_username:
            user.discord_username = discord_username
            await session.flush()
        return user

    @staticmethod
    async def link_uva(
        session: AsyncSession,
        discord_user_id: int,
        uva_username: str,
        uva_user_id: int,
        discord_username: Optional[str] = None
    ) -> User:
        user = await UserRepository.get_or_create(session, discord_user_id, discord_username)
        user.uva_username = uva_username
        user.uva_user_id = uva_user_id
        await session.flush()
        return user

    @staticmethod
    async def unlink_uva(
        session: AsyncSession,
        discord_user_id: int
    ) -> Optional[User]:
        user = await UserRepository.get_by_discord_id(session, discord_user_id)
        if user:
            user.uva_username = None
            user.uva_user_id = None
            await session.flush()
        return user
