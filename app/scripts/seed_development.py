"""Explicit development-only fixture import; never called by startup/migrations."""
import argparse
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Problem
from app.repositories.problem_repo import ProblemRepository


async def seed():
    if settings.APP_ENV not in {"development", "test"}:
        raise RuntimeError("Development fixture cannot be imported in production")
    from sqlalchemy.engine import make_url
    database_name = make_url(settings.DATABASE_URL).database or ""
    if not any(marker in database_name.lower() for marker in ("development", "integration", "test")):
        raise RuntimeError("Use a separate database whose name contains development, integration or test")
    fixture = json.loads((Path(__file__).parents[2] / "tests/fixtures/uva100_development.json").read_text(encoding="utf-8"))
    if fixture.get("official_judge_data") is not False:
        raise RuntimeError("Fixture must explicitly declare nonofficial data")
    data = fixture["problem"].copy()
    data["test_cases"] = json.dumps(data["test_cases"])
    async with AsyncSessionLocal() as session:
        existing = await ProblemRepository.get_by_number(session, data["problem_number"])
        if existing:
            # Preserve existing operator-managed statements/test cases.
            print(f"UVa 100 already exists at /problems/{existing.id}; no data changed")
            return
        problem = Problem(**data)
        session.add(problem)
        await session.commit()
        print(f"Imported nonofficial development fixture at /problems/{problem.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-development-database", required=True, action="store_true")
    parser.parse_args()
    asyncio.run(seed())
