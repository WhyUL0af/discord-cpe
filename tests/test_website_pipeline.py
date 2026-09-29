"""Provider-neutral mock workflow, authorization and input boundary checks."""
import asyncio
import json

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import func, select

from app import web
from app.models import Problem, Submission, UserSolvedProblem
from app.providers.judge_factory import get_judge_provider, validate_judge_configuration
from app.providers.judge_provider import Verdict, LANGUAGES, JudgeResult
from app.providers.mock_judge_provider import MockJudgeProvider
from app.services.website_judge_service import CodePayload, WebsiteSubmissionService, clean_compiler_message
from tests.test_website_judge import site, create_fixture, login_cookie


def use_mock(verdict=Verdict.ACCEPTED):
    provider = MockJudgeProvider(verdict, delay=0)
    web.app.dependency_overrides[get_judge_provider] = lambda: provider
    return provider


@pytest.mark.asyncio
async def test_problem_search_filters_and_hidden_projection(site):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    async with factory() as session:
        problem = await session.get(Problem, problem_id)
        cases = json.loads(problem.test_cases)
        cases.append({"input": "PRIVATE_STDIN_SENTINEL", "output": "PRIVATE_EXPECTED_SENTINEL", "hidden": True})
        problem.test_cases = json.dumps(cases)
        session.add(Problem(problem_number=272, title="TEX Quotes", difficulty="⭐⭐"))
        session.add(UserSolvedProblem(user_id=users[0], problem_id=problem_id))
        await session.commit()
    client.cookies.set("session", login_cookie(users[0]))
    for url in (f"/api/problems/{problem_id}", "/api/problems", f"/problems/{problem_id}", "/problems"):
        response = await client.get(url)
        assert response.status_code == 200
        assert "PRIVATE_STDIN_SENTINEL" not in response.text
        assert "PRIVATE_EXPECTED_SENTINEL" not in response.text
        assert "test_cases" not in response.text
    for params, expected in (({"q": "100"}, [100]), ({"q": "Quotes"}, [272]),
                              ({"difficulty": "⭐⭐"}, [272]), ({"solved": "solved"}, [100]),
                              ({"solved": "unsolved"}, [272])):
        response = await client.get("/api/problems", params=params)
        assert [p["problem_number"] for p in response.json()] == expected
    assert (await client.get("/api/problems", params={"solved": "bogus"})).status_code == 422
    client.cookies.clear()
    assert (await client.get("/api/problems", params={"solved": "solved"})).status_code == 401
    assert (await client.get(f"/problems/{problem_id}")).status_code == 303
    assert (await client.get("/api/problems/999999")).status_code == 404


@pytest.mark.asyncio
async def test_workspace_rendering_language_configs_and_static_assets(site):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))
    html = (await client.get(f"/problems/{problem_id}")).text
    for text in ("C++17", "C17", "Python 3", "Java 21", "problem-pane", "console-pane", "workspace-config", "Memory limit: 131072", "Sample Input", "Sample Output"):
        assert text in html
    assert (await client.get("/static/workspace.js")).status_code == 200
    assert (await client.get("/static/workspace.css")).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["cpp", "c", "python", "java"])
async def test_mock_run_and_submit_language_metadata(site, language):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))
    use_mock()
    payload = {"problem_id": problem_id, "code": "not an executable program", "language": language}
    run = await client.post("/api/run", json=payload)
    assert run.json()["mock"] is True
    assert "1 10 20" in run.json()["stdout"]
    custom = await client.post("/api/run", json={**payload, "input_mode": "custom", "input": ""})
    assert custom.json()["input"] == ""
    assert "not executed" in custom.json()["stdout"]
    async with factory() as session:
        assert await session.scalar(select(func.count(Submission.id))) == 0
        assert await session.scalar(select(func.count(UserSolvedProblem.id))) == 0
    response = await client.post("/api/submissions", json=payload)
    assert response.json()["status"] == "queued"
    detail = (await client.get(f"/api/submissions/{response.json()['submission_id']}")).json()
    assert detail["status"] == "finished"
    assert detail["verdict"] == "ACCEPTED"
    assert detail["total_tests"] == detail["passed_tests"] == 4
    assert detail["started_at"] and detail["finished_at"]
    assert detail["language"] == LANGUAGES[language]["label"]


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", list(Verdict))
async def test_deterministic_mock_verdicts(site, verdict):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))
    use_mock(verdict)
    created = await client.post("/api/submissions", json={"problem_id": problem_id, "language": "cpp", "code": "same source for every scenario"})
    data = (await client.get(f"/api/submissions/{created.json()['submission_id']}")).json()
    assert data["verdict"] == verdict.value
    assert data["status"] == "finished"
    assert data["failure"] is None
    if verdict == Verdict.COMPILATION_ERROR:
        assert "simulated compilation failure" in data["compiler_message"]
    async with factory() as session:
        assert await session.scalar(select(func.count(UserSolvedProblem.id))) == int(verdict == Verdict.ACCEPTED)


@pytest.mark.asyncio
async def test_queued_running_finished_are_persisted_and_observable(site, monkeypatch):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))
    started, release = asyncio.Event(), asyncio.Event()

    class GatedMock(MockJudgeProvider):
        async def submit(self, request, cases):
            started.set()
            await release.wait()
            return await super().submit(request, cases)

    provider = GatedMock(delay=0)
    web.app.dependency_overrides[get_judge_provider] = lambda: provider
    tasks = []
    monkeypatch.setattr(BackgroundTasks, "add_task", lambda self, func, *args, **kwargs: tasks.append((func, args, kwargs)))
    created = await client.post("/api/submissions", json={"problem_id": problem_id, "language": "cpp", "code": "draft"})
    submission_id = created.json()["submission_id"]
    assert (await client.get(f"/api/submissions/{submission_id}")).json()["status"] == "queued"
    func_, args, kwargs = tasks[0]
    task = asyncio.create_task(func_(*args, **kwargs))
    try:
        await asyncio.wait_for(started.wait(), 2)
        assert (await client.get(f"/api/submissions/{submission_id}")).json()["status"] == "running"
    finally:
        release.set()
        await task
    assert (await client.get(f"/api/submissions/{submission_id}")).json()["status"] == "finished"


@pytest.mark.asyncio
async def test_duplicate_ac_ownership_and_history(site):
    client, factory = site
    users, problem_id = await create_fixture(factory, users=2)
    client.cookies.set("session", login_cookie(users[0]))
    use_mock()
    for _ in range(2):
        created = await client.post("/api/submissions", json={"problem_id": problem_id, "language": "java", "code": "PRIVATE_SOURCE"})
    sub_id = created.json()["submission_id"]
    history = await client.get("/submissions")
    assert "Mock" in history.text and "Memory (KB)" in history.text
    assert "PRIVATE_SOURCE" in (await client.get(f"/submissions/{sub_id}")).text
    async with factory() as session:
        assert await session.scalar(select(func.count(UserSolvedProblem.id))) == 1
    client.cookies.set("session", login_cookie(users[1]))
    for url in (f"/api/submissions/{sub_id}", f"/api/submissions/{sub_id}/code", f"/submissions/{sub_id}"):
        response = await client.get(url)
        assert response.status_code == 404
        assert "PRIVATE_SOURCE" not in response.text
    assert (await client.get("/api/submissions")).json() == []
    client.cookies.clear()
    assert (await client.get(f"/api/submissions/{sub_id}")).status_code == 401
    assert (await client.post("/api/submissions", json={"problem_id": problem_id, "language": "cpp", "code": "x"})).status_code == 401


@pytest.mark.asyncio
async def test_server_rejects_invalid_and_untrusted_submission_fields(site):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))
    use_mock()
    base = {"problem_id": problem_id, "language": "cpp", "code": "x"}
    for values, status in (({"problem_id": 999999}, 404), ({"language": "ruby"}, 422),
                           ({"code": "a" * (262144 + 1)}, 422), ({"code": "界" * 90000}, 422),
                           ({"user_id": users[1] if len(users) > 1 else 22}, 422),
                           ({"verdict": "ACCEPTED"}, 422), ({"runtime": 1}, 422), ({"passed_tests": 4}, 422)):
        assert (await client.post("/api/submissions", json={**base, **values})).status_code == status
    async with factory() as session:
        assert await session.scalar(select(func.count(Submission.id))) == 0
    assert (await client.post("/api/submissions", json=base, headers={"Origin": "https://evil.example"})).status_code == 403


@pytest.mark.asyncio
async def test_provider_error_finishes_as_internal_error(site):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))

    class Broken(MockJudgeProvider):
        async def submit(self, request, cases):
            raise RuntimeError("PRIVATE_INTERNAL_SECRET")

    web.app.dependency_overrides[get_judge_provider] = lambda: Broken(delay=0)
    created = await client.post("/api/submissions", json={"problem_id": problem_id, "language": "cpp", "code": "draft"})
    result = await client.get(f"/api/submissions/{created.json()['submission_id']}")
    assert result.json()["verdict"] == "INTERNAL_ERROR"
    assert "PRIVATE_INTERNAL_SECRET" not in result.text


@pytest.mark.asyncio
async def test_service_rejects_provider_hidden_failure_details(site):
    client, factory = site
    users, problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(users[0]))

    class Leaky(MockJudgeProvider):
        async def submit(self, request, cases):
            return JudgeResult(Verdict.WRONG_ANSWER, total_tests=len(cases), public_failure={
                "test_case": 3, "input": "PRIVATE_HIDDEN_INPUT", "expected": "PRIVATE_HIDDEN_OUTPUT", "output": "PRIVATE_HIDDEN_RESULT"})

    web.app.dependency_overrides[get_judge_provider] = lambda: Leaky(delay=0)
    created = await client.post("/api/submissions", json={"problem_id": problem_id, "language": "cpp", "code": "draft"})
    response = await client.get(f"/api/submissions/{created.json()['submission_id']}")
    assert response.json()["failure"] is None
    assert "PRIVATE_HIDDEN" not in response.text


@pytest.mark.asyncio
async def test_production_mock_guard_on_startup_and_selection(monkeypatch):
    monkeypatch.setattr(web.settings, "APP_ENV", "production")
    monkeypatch.setattr(web.settings, "JUDGE_PROVIDER", "mock")
    with pytest.raises(RuntimeError, match="development/test only"):
        get_judge_provider()
    with pytest.raises(RuntimeError):
        async with web.lifespan(web.app):
            pass
    monkeypatch.setattr(web.settings, "APP_ENV", "development")
    assert get_judge_provider().development_only


def test_compiler_output_is_fail_closed_and_bounded():
    raw = "/app/private/main.cpp:1: error: expected ';' SECRET_TOKEN=secret\nENV=secret\ng++ /app/private/main.cpp\nC:\\private\\file\n"
    cleaned = clean_compiler_message(raw * 1000)
    assert len(cleaned) <= 2048
    for secret in ("/app", "C:\\", "SECRET", "ENV", "g++", "private"):
        assert secret not in cleaned
    assert "expected" in cleaned


def test_source_maximum_is_bytes_not_characters():
    assert len(CodePayload(language="cpp", code="x" * 262144).code) == 262144
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CodePayload(language="cpp", code="界" * 87382)


@pytest.mark.asyncio
async def test_fixture_seed_is_refused_in_production_and_nondevelopment_database(monkeypatch):
    from app.scripts.seed_development import seed
    monkeypatch.setattr(web.settings, "APP_ENV", "production")
    with pytest.raises(RuntimeError, match="production"):
        await seed()
    monkeypatch.setattr(web.settings, "APP_ENV", "development")
    monkeypatch.setattr(web.settings, "DATABASE_URL", "postgresql+asyncpg://unused:unused@invalid/cpe_bot")
    with pytest.raises(RuntimeError, match="separate database"):
        await seed()


@pytest.mark.asyncio
async def test_explicit_development_seed_is_idempotent_and_preserves_existing_data(site, monkeypatch):
    from app.scripts import seed_development
    _, factory = site
    monkeypatch.setattr(web.settings, "APP_ENV", "development")
    monkeypatch.setattr(web.settings, "DATABASE_URL", "sqlite+aiosqlite:///fixture_test.sqlite3")
    monkeypatch.setattr(seed_development, "AsyncSessionLocal", factory)
    await seed_development.seed()
    async with factory() as session:
        problem = await session.scalar(select(Problem).where(Problem.problem_number == 100))
        problem.statement = "Operator maintained description"
        await session.commit()
    await seed_development.seed()
    async with factory() as session:
        assert await session.scalar(select(func.count(Problem.id))) == 1
        assert (await session.scalar(select(Problem))).statement == "Operator maintained description"
