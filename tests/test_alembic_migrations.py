import os
import tempfile
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command


def test_all_alembic_revision_ids_within_32_characters():
    """PostgreSQL alembic_version.version_num is VARCHAR(32).
    Ensure every revision ID in alembic/versions is <= 32 characters.
    """
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    
    for rev in script.walk_revisions():
        assert len(rev.revision) <= 32, (
            f"Revision ID '{rev.revision}' exceeds 32 characters limit (length={len(rev.revision)})"
        )
        if rev.down_revision:
            if isinstance(rev.down_revision, tuple):
                for down in rev.down_revision:
                    assert len(down) <= 32, f"Down revision ID '{down}' exceeds 32 characters limit"
            else:
                assert len(rev.down_revision) <= 32, (
                    f"Down revision ID '{rev.down_revision}' exceeds 32 characters limit"
                )


def test_alembic_migration_chain_and_heads():
    """Verify single head and valid migration history chain."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected single head, got: {heads}"
    assert heads[0] == "0003_practice_center"

    # Walk from head to base to ensure no disconnected branches
    revisions = [rev.revision for rev in script.walk_revisions()]
    assert revisions == ["0003_practice_center", "0002_guild_daily_problems", "0001_initial_schema"]


def test_alembic_upgrade_and_downgrade_lifecycle():
    """Test full upgrade to head, downgrade to 0002, and re-upgrade to 0003 head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        sqlite_url = f"sqlite+aiosqlite:///{temp_db_path.replace(os.sep, '/')}"
        os.environ["DATABASE_URL"] = sqlite_url

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade from base to 0002
        command.upgrade(alembic_cfg, "0002_guild_daily_problems")

        # 2. Upgrade from 0002 to 0003 (head)
        command.upgrade(alembic_cfg, "head")

        # 3. Downgrade from 0003 back to 0002
        command.downgrade(alembic_cfg, "0002_guild_daily_problems")

        # 4. Re-upgrade from 0002 to 0003 (idempotent / transaction safe)
        command.upgrade(alembic_cfg, "head")

    finally:
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
