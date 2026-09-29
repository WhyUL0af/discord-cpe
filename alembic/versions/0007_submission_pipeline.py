"""Add website submission lifecycle; preserve Bot verdicts and existing rows."""
from alembic import op
import sqlalchemy as sa

revision = "0007_submission_pipeline"
down_revision = "0006_submission_failure_details"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("submissions", sa.Column("status", sa.String(16), server_default="FINISHED", nullable=False))
    op.add_column("submissions", sa.Column("judge_provider", sa.String(32), nullable=True))
    for name in ("passed_tests", "total_tests"):
        op.add_column("submissions", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("compiler_message", sa.Text(), nullable=True))
    for name in ("started_at", "finished_at"):
        op.add_column("submissions", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE submissions SET status='QUEUED' WHERE source='website' AND verdict='Pending'")
    op.execute("UPDATE submissions SET status='RUNNING' WHERE source='website' AND verdict='Judging'")


def downgrade():
    for name in ("finished_at", "started_at", "compiler_message", "total_tests", "passed_tests", "judge_provider", "status"):
        op.drop_column("submissions", name)
