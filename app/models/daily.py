from datetime import date
from typing import Optional
from sqlalchemy import BigInteger, Date, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DailyProblem(Base):
    __tablename__ = "daily_problems"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    discord_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Relationships
    problem = relationship("Problem", back_populates="daily_problems")

    def __repr__(self) -> str:
        return f"<DailyProblem date={self.date} problem_id={self.problem_id}>"
