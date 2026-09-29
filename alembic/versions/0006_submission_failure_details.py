"""Persist public judge failure details without truncating output.

Revision ID: 0006_submission_failure_details
Revises: 0005_problem_memory_limit
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006_submission_failure_details"
down_revision: Union[str, None] = "0005_problem_memory_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("failure_details", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "failure_details")
