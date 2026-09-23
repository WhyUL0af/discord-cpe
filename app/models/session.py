from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActiveProblemSession(Base):
    __tablename__ = "active_problem_sessions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False)
    thread_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    last_submission_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active, solved, closed
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    solved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions", lazy="selectin")
    problem = relationship("Problem", back_populates="sessions", lazy="selectin")

    __table_args__ = (
        Index("ix_active_user_problem", "user_id", "problem_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<ActiveProblemSession id={self.id} user_id={self.user_id} problem_id={self.problem_id} status={self.status}>"
