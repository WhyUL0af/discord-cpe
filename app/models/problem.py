from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    problem_number: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    uhunt_pid: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(100), default="UVa Online Judge", nullable=False)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    time_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in milliseconds
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
    sessions = relationship("ActiveProblemSession", back_populates="problem")
    submissions = relationship("Submission", back_populates="problem")
    solved_by = relationship("UserSolvedProblem", back_populates="problem")
    daily_problems = relationship("DailyProblem", back_populates="problem")

    def __repr__(self) -> str:
        return f"<Problem #{self.problem_number}: {self.title} ({self.difficulty or 'Unknown'})>"
