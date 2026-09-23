from datetime import date
from typing import Optional
from sqlalchemy import BigInteger, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyProblem(Base):
    __tablename__ = "daily_problems"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    discord_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Relationships - enforce selectin eager loading to prevent MissingGreenlet in async context
    problem = relationship("Problem", back_populates="daily_problems", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("guild_id", "date", name="uq_guild_daily_problem"),
    )

    def __repr__(self) -> str:
        return f"<DailyProblem guild_id={self.guild_id} date={self.date} problem_id={self.problem_id}>"
