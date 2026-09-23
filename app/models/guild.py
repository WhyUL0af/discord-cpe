from typing import Optional
from sqlalchemy import BigInteger, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GuildSettings(Base):
    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    daily_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    practice_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    ranking_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    discussion_channel_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    ranking_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    practice_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    archive_thread_on_solve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<GuildSettings guild_id={self.guild_id}>"
