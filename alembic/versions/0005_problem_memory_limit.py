"""Store per-problem judge memory limit.

Revision ID: 0005_problem_memory_limit
Revises: 0004_website_practice
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_problem_memory_limit"
down_revision: Union[str, None] = "0004_website_practice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("problems", sa.Column("memory_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("problems", "memory_limit")
