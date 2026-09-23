from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserSolvedProblem(Base):
    __tablename__ = "user_solved_problems"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False)
    first_accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="solved_problems", lazy="selectin")
    problem = relationship("Problem", back_populates="solved_by", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("user_id", "problem_id", name="uq_user_solved_problem"),
    )

    def __repr__(self) -> str:
        return f"<UserSolvedProblem user_id={self.user_id} problem_id={self.problem_id}>"
