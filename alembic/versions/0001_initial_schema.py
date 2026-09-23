"""Initial schema for CPE Discord Bot

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("discord_user_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_username", sa.String(length=64), nullable=True),
        sa.Column("uva_username", sa.String(length=64), nullable=True),
        sa.Column("uva_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_discord_user_id"), "users", ["discord_user_id"], unique=True)
    op.create_index(op.f("ix_users_uva_username"), "users", ["uva_username"], unique=False)
    op.create_index(op.f("ix_users_uva_user_id"), "users", ["uva_user_id"], unique=False)

    # problems
    op.create_table(
        "problems",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("problem_number", sa.Integer(), nullable=False),
        sa.Column("uhunt_pid", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("time_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_problems_problem_number"), "problems", ["problem_number"], unique=True)
    op.create_index(op.f("ix_problems_uhunt_pid"), "problems", ["uhunt_pid"], unique=True)

    # guild_settings
    op.create_table(
        "guild_settings",
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("daily_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("practice_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("ranking_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("discussion_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("ranking_message_id", sa.BigInteger(), nullable=True),
        sa.Column("archive_thread_on_solve", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("guild_id"),
    )

    # active_problem_sessions
    op.create_table(
        "active_problem_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("last_submission_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_active_problem_sessions_problem_id"), "active_problem_sessions", ["problem_id"], unique=False)
    op.create_index(op.f("ix_active_problem_sessions_thread_id"), "active_problem_sessions", ["thread_id"], unique=True)
    op.create_index(op.f("ix_active_problem_sessions_user_id"), "active_problem_sessions", ["user_id"], unique=False)
    op.create_index("ix_active_user_problem", "active_problem_sessions", ["user_id", "problem_id", "status"], unique=False)

    # submissions
    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("external_submission_id", sa.BigInteger(), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=False),
        sa.Column("runtime", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_submissions_external_submission_id"), "submissions", ["external_submission_id"], unique=True)
    op.create_index(op.f("ix_submissions_problem_id"), "submissions", ["problem_id"], unique=False)
    op.create_index(op.f("ix_submissions_user_id"), "submissions", ["user_id"], unique=False)

    # user_solved_problems
    op.create_table(
        "user_solved_problems",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("first_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "problem_id", name="uq_user_solved_problem"),
    )
    op.create_index(op.f("ix_user_solved_problems_problem_id"), "user_solved_problems", ["problem_id"], unique=False)
    op.create_index(op.f("ix_user_solved_problems_user_id"), "user_solved_problems", ["user_id"], unique=False)

    # daily_problems
    op.create_table(
        "daily_problems",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("problem_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_message_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_daily_problems_date"), "daily_problems", ["date"], unique=True)


def downgrade() -> None:
    op.drop_table("daily_problems")
    op.drop_table("user_solved_problems")
    op.drop_table("submissions")
    op.drop_table("active_problem_sessions")
    op.drop_table("guild_settings")
    op.drop_table("problems")
    op.drop_table("users")
