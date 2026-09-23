"""Add guild_id and uq_guild_daily_problem constraint to daily_problems

Revision ID: 0002_guild_daily_problems
Revises: 0001_initial_schema
Create Date: 2026-09-23 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_guild_daily_problems"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use batch_alter_table for universal compatibility across PostgreSQL and SQLite
    with op.batch_alter_table("daily_problems") as batch_op:
        batch_op.add_column(
            sa.Column("guild_id", sa.BigInteger(), nullable=False, server_default="0")
        )
        batch_op.create_index(batch_op.f("ix_daily_problems_guild_id"), ["guild_id"], unique=False)
        try:
            batch_op.drop_index("ix_daily_problems_date")
        except Exception:
            pass
        batch_op.create_index("ix_daily_problems_date", ["date"], unique=False)
        batch_op.create_unique_constraint("uq_guild_daily_problem", ["guild_id", "date"])


def downgrade() -> None:
    with op.batch_alter_table("daily_problems") as batch_op:
        batch_op.drop_constraint("uq_guild_daily_problem", type_="unique")
        batch_op.drop_index("ix_daily_problems_date")
        batch_op.create_index("ix_daily_problems_date", ["date"], unique=True)
        batch_op.drop_index(batch_op.f("ix_daily_problems_guild_id"))
        batch_op.drop_column("guild_id")
