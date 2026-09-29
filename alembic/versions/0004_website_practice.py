"""Add website profile, statements and Judge0 submissions.

Revision ID: 0004_website_practice
Revises: 0003_practice_center
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_website_practice"
down_revision: Union[str, None] = "0003_practice_center"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("discord_avatar", sa.String(255), nullable=True))
    op.add_column("problems", sa.Column("category", sa.String(64), nullable=True))
    for name in ("statement", "input_description", "output_description", "sample_input", "sample_output", "test_cases"):
        op.add_column("problems", sa.Column(name, sa.Text(), nullable=True))
    op.add_column("problems", sa.Column("discussion_url", sa.String(500), nullable=True))
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column("external_submission_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("submissions", sa.Column("memory", sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("language", sa.String(32), nullable=True))
    op.add_column("submissions", sa.Column("source", sa.String(20), server_default="uhunt", nullable=False))
    op.add_column("submissions", sa.Column("code", sa.Text(), nullable=True))
    op.add_column("submissions", sa.Column("judge_token", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "judge_token")
    op.drop_column("submissions", "code")
    op.drop_column("submissions", "source")
    op.drop_column("submissions", "language")
    op.drop_column("submissions", "memory")
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column("external_submission_id", existing_type=sa.BigInteger(), nullable=False)
    for name in ("discussion_url", "test_cases", "sample_output", "sample_input", "output_description", "input_description", "statement"):
        op.drop_column("problems", name)
    op.drop_column("problems", "category")
    op.drop_column("users", "discord_avatar")
