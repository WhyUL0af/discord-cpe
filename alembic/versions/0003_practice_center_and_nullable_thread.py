"""Allow nullable thread_id and add practice_message_id to guild_settings

Revision ID: 0003_practice_center_and_nullable_thread
Revises: 0002_guild_daily_problems
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_practice_center_and_nullable_thread"
down_revision: Union[str, None] = "0002_guild_daily_problems"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update active_problem_sessions: thread_id nullable and non-unique
    with op.batch_alter_table("active_problem_sessions") as batch_op:
        batch_op.alter_column(
            "thread_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )
        try:
            batch_op.drop_index("ix_active_problem_sessions_thread_id")
        except Exception:
            pass
        batch_op.create_index(
            "ix_active_problem_sessions_thread_id",
            ["thread_id"],
            unique=False,
        )

    # 2. Add practice_message_id to guild_settings
    with op.batch_alter_table("guild_settings") as batch_op:
        batch_op.add_column(
            sa.Column("practice_message_id", sa.BigInteger(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("guild_settings") as batch_op:
        batch_op.drop_column("practice_message_id")

    with op.batch_alter_table("active_problem_sessions") as batch_op:
        try:
            batch_op.drop_index("ix_active_problem_sessions_thread_id")
        except Exception:
            pass
        batch_op.create_index(
            "ix_active_problem_sessions_thread_id",
            ["thread_id"],
            unique=True,
        )
        batch_op.alter_column(
            "thread_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
