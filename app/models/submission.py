from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    problem_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="CASCADE"), index=True, nullable=False)
    external_submission_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    runtime: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in ms
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="submissions", lazy="selectin")
    problem = relationship("Problem", back_populates="submissions", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Submission ext_id={self.external_submission_id} verdict={self.verdict}>"
