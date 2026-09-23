from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    discord_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    discord_username: Mapped[str] = mapped_column(String(64), nullable=True)
    uva_username: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    uva_user_id: Mapped[int] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    sessions = relationship("ActiveProblemSession", back_populates="user", cascade="all, delete-orphan")
    submissions = relationship("Submission", back_populates="user", cascade="all, delete-orphan")
    solved_problems = relationship("UserSolvedProblem", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User discord_id={self.discord_user_id} uva_user={self.uva_username}>"
