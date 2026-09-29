from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
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
    external_submission_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    runtime: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in ms
    memory: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in KB
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="uhunt", server_default="uhunt", nullable=False)
    code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    judge_token: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="FINISHED", server_default="FINISHED", nullable=False)
    judge_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    passed_tests: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tests: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compiler_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
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
