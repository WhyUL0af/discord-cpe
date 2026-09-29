"""Disposable browser QA app. Never included as a production entrypoint.

Start only with APP_ENV=test and a dedicated sqlite development/test database.
The test session endpoint exists only in this module, not app.web.
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse

from app import web
from app.database import Base, engine, AsyncSessionLocal
from app.models import Problem, User
from app.repositories.problem_repo import ProblemRepository
from app.repositories.user_repo import UserRepository
from app.providers.judge_provider import Verdict

if web.settings.APP_ENV != "test" or not web.settings.DATABASE_URL.startswith("sqlite+") or "test" not in web.settings.DATABASE_URL:
    raise RuntimeError("Browser fixture requires APP_ENV=test and a disposable SQLite test database")


@asynccontextmanager
async def qa_lifespan(app):
    web.validate_judge_configuration()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await UserRepository.get_or_create(session, 900000, "Browser Test User")
        if not await ProblemRepository.get_by_number(session, 100):
            data = json.loads((Path(__file__).parent / "fixtures/uva100_development.json").read_text(encoding="utf-8"))["problem"]
            data["test_cases"] = json.dumps(data["test_cases"])
            session.add(Problem(**data))
        await session.commit()
    yield
    await engine.dispose()


app = web.app
app.router.lifespan_context = qa_lifespan


@app.get("/__test/session")
async def test_session(request: Request):
    async with AsyncSessionLocal() as session:
        user = await UserRepository.get_by_discord_id(session, 900000)
        request.session.clear()
        request.session["user_id"] = user.id
    return RedirectResponse("/problems", status_code=303)


@app.get("/__test/scenario/{verdict}")
async def test_scenario(verdict: Verdict):
    # Explicit QA fixture configuration, never derived from submitted source.
    web.settings.JUDGE_MOCK_VERDICT = verdict.value
    async with AsyncSessionLocal() as session:
        problem = await ProblemRepository.get_by_number(session, 100)
    return RedirectResponse(f"/problems/{problem.id}", status_code=303)
