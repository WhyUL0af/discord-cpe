import os
import tempfile
import sqlite3
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
    assert heads[0] == "0007_submission_pipeline"

    # Walk from head to base to ensure no disconnected branches
    revisions = [rev.revision for rev in script.walk_revisions()]
    assert revisions == [
        "0007_submission_pipeline",
        "0006_submission_failure_details",
        "0005_problem_memory_limit",
        "0004_website_practice",
        "0003_practice_center",
        "0002_guild_daily_problems",
        "0001_initial_schema",
    ]


def test_alembic_upgrade_and_downgrade_lifecycle():
    """Test full upgrade to head, downgrade to 0002, and re-upgrade to current head."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        sqlite_url = f"sqlite+aiosqlite:///{temp_db_path.replace(os.sep, '/')}"
        original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = sqlite_url

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)

        # 1. Upgrade from base to 0002
        command.upgrade(alembic_cfg, "0002_guild_daily_problems")

        # 2. Upgrade from 0002 to current head
        command.upgrade(alembic_cfg, "head")

        # 3. Downgrade from current head back to 0002
        command.downgrade(alembic_cfg, "0002_guild_daily_problems")

        # 4. Re-upgrade from 0002 to current head
        command.upgrade(alembic_cfg, "head")

    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


def test_pipeline_migration_preserves_existing_bot_and_website_data(tmp_path, monkeypatch):
    database = tmp_path / "migration_test.sqlite3"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0006_submission_failure_details")
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO users (id, discord_user_id, created_at, updated_at) VALUES (1, 900000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO problems (id, problem_number, title, source, created_at, updated_at) VALUES (1, 100, 'Preserved', 'UVa', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        for sid, source, verdict in ((1, "uhunt", "Accepted"), (2, "website", "Pending"), (3, "website", "Judging")):
            conn.execute("INSERT INTO submissions (id,user_id,problem_id,source,verdict,code,submitted_at) VALUES (?,1,1,?,?,?,CURRENT_TIMESTAMP)",
                         (sid, source, verdict, "preserved source"))
    command.upgrade(cfg, "head")
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT status, verdict, code FROM submissions ORDER BY id").fetchall() == [
            ("FINISHED", "Accepted", "preserved source"), ("QUEUED", "Pending", "preserved source"),
            ("RUNNING", "Judging", "preserved source")]
        assert conn.execute("SELECT title FROM problems").fetchone()[0] == "Preserved"
