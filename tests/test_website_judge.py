"""Website-to-Judge0 contract tests using a development-only UVa 100 fixture."""
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from itsdangerous import TimestampSigner
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import web
from app.database import Base
from app.models import Problem, Submission, User, UserSolvedProblem
from app.repositories.ranking_repo import RankingRepository
from app.services.ranking_service import RankingService
from app.bot.views.problem_view import DailyProblemView

SESSION_SIGNING_SECRET = "test-session-secret-that-is-long-enough-123456"

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "uva100_development.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
EXPECTED = {
    "1 10\n100 200\n": "1 10 20\n100 200 125\n",
    "10 1\n": "10 1 20\n",
    "201 210\n900 1000\n": "201 210 89\n900 1000 174\n",
    "1 1\n": "1 1 1\n",
    "7 7\n": "7 7 17\n",
}


@pytest.fixture
async def site(monkeypatch):
    monkeypatch.setattr(web.settings, "APP_ENV", "test")
    monkeypatch.setattr(web.settings, "JUDGE_PROVIDER", "disabled")
    monkeypatch.setattr(web.settings, "WEBSITE_SESSION_SECRET", SESSION_SIGNING_SECRET)
    monkeypatch.setattr(web.settings, "DISCORD_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(web.settings, "DISCORD_OAUTH_CLIENT_SECRET", "test-client-secret")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(web, "AsyncSessionLocal", factory)
    web.app.dependency_overrides.clear()
    middleware = next(m for m in web.app.user_middleware if m.cls.__name__ == "SessionMiddleware")
    monkeypatch.setitem(middleware.kwargs, "secret_key", SESSION_SIGNING_SECRET)
    monkeypatch.setitem(middleware.kwargs, "https_only", True)
    web.app.middleware_stack = None
    transport = httpx.ASGITransport(app=web.app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client, factory
    web.app.dependency_overrides.clear()
    web.app.middleware_stack = None
    await engine.dispose()


def login_cookie(user_id: int) -> str:
    payload = base64.b64encode(json.dumps({"user_id": user_id}, separators=(",", ":")).encode())
    return TimestampSigner(SESSION_SIGNING_SECRET).sign(payload).decode()


async def create_fixture(factory, users=1):
    async with factory() as session:
        people = [User(discord_user_id=900000 + i, discord_username=f"Student {i}") for i in range(users)]
        session.add_all(people)
        problem_data = FIXTURE["problem"].copy()
        problem_data["test_cases"] = json.dumps(problem_data["test_cases"])
        problem = Problem(**problem_data)
        session.add(problem)
        await session.commit()
        return [person.id for person in people], problem.id


def fake_judge(monkeypatch, extra_handler=None):
    real_client = httpx.AsyncClient
    requests = []

    def handle(request):
        if request.url.path.endswith("/submissions"):
            payload = json.loads(request.content)
            requests.append(payload)
            code = payload["source_code"]
            if "COMPILE_ERROR" in code:
                result = {"status": {"id": 6, "description": "Compilation Error"}, "compile_output": "compiler error", "stdout": None}
            elif "RUNTIME_ERROR" in code:
                result = {"status": {"id": 7, "description": "Runtime Error (NZEC)"}, "stderr": "runtime error", "stdout": None}
            elif "TIMEOUT" in code:
                result = {"status": {"id": 5, "description": "Time Limit Exceeded (SIGTERM)"}, "stdout": ""}
            elif "WRONG_ANSWER" in code:
                result = {"status": {"id": 4, "description": "Wrong Answer"}, "stdout": "incorrect\n"}
            elif "HIDDEN_FAIL" in code and payload["stdin"].startswith("201 "):
                result = {"status": {"id": 4, "description": "Wrong Answer"}, "stdout": "hidden output\n"}
            else:
                result = {"status": {"id": 3, "description": "Accepted"}, "stdout": EXPECTED.get(payload["stdin"], ""), "time": "0.012", "memory": 4096}
            return httpx.Response(200, json=result)
        if extra_handler:
            return extra_handler(request)
        return httpx.Response(404)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(web.settings, "JUDGE0_URL", "http://judge.test")
    monkeypatch.setattr(web.settings, "JUDGE_PROVIDER", "judge0")
    return requests


@pytest.mark.asyncio
async def test_problem_page_and_run_sample_custom_does_not_create_submission(site, monkeypatch):
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(user_id))
    requests = fake_judge(monkeypatch)

    page = await client.get(f"/problems/{problem_id}")
    assert page.status_code == 200
    assert "The 3n + 1 Problem" in page.text
    sample = await client.post(f"/api/problems/{problem_id}/run", json={"language": "cpp", "code": "solution", "input": ""})
    assert sample.status_code == 200
    assert sample.json()["result"] == "Accepted"
    assert requests[-1]["stdin"] == FIXTURE["problem"]["sample_input"]
    for language, language_id in (("c", 50), ("cpp", 54), ("python", 71)):
        response = await client.post(f"/api/problems/{problem_id}/run", json={"language": language, "code": "solution", "input": "7 7\n"})
        assert response.status_code == 200
        assert response.json()["result"] == "Accepted"
        assert requests[-1]["language_id"] == language_id
        assert requests[-1]["source_code"] == "solution"
        assert requests[-1]["stdin"] == "7 7\n"
        assert requests[-1]["memory_limit"] == 131072

    async with factory() as session:
        assert await session.scalar(select(func.count(Submission.id))) == 0
        assert await session.scalar(select(func.count(UserSolvedProblem.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("language", "language_id"), [("c", 50), ("cpp", 54), ("python", 71)])
async def test_supported_languages_submit_through_backend(site, monkeypatch, language, language_id):
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(user_id))
    requests = fake_judge(monkeypatch)
    created = await client.post(f"/api/problems/{problem_id}/submit", json={"language": language, "code": "solution"})
    checked = await client.get(f"/api/submissions/{created.json()['submission_id']}")
    assert checked.json()["result"] == "Accepted"
    assert requests[0]["language_id"] == language_id
    assert requests[0]["memory_limit"] == 131072


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected"),
    [("solution", "Accepted"), ("WRONG_ANSWER", "Wrong Answer"), ("COMPILE_ERROR", "Compilation Error"), ("RUNTIME_ERROR", "Runtime Error"), ("TIMEOUT", "Time Limit Exceeded")],
)
async def test_submit_verdicts_are_persisted(site, monkeypatch, code, expected):
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(user_id))
    fake_judge(monkeypatch)

    created = await client.post(f"/api/problems/{problem_id}/submit", json={"language": "cpp", "code": code})
    assert created.status_code == 200
    submission_id = created.json()["submission_id"]
    assert created.json()["result"] == "Pending"
    result = await client.get(f"/api/submissions/{submission_id}")
    assert result.json()["result"] == expected
    async with factory() as session:
        row = await session.get(Submission, submission_id)
        assert row.source == "website"
        assert row.code == code
        assert row.verdict == expected
        assert (await session.scalar(select(func.count(UserSolvedProblem.id)))) == (1 if expected == "Accepted" else 0)
        if expected == "Wrong Answer":
            assert json.loads(row.failure_details)["test_case"] == 1


@pytest.mark.asyncio
async def test_duplicate_acceptances_count_once_and_submission_code_is_private(site, monkeypatch):
    client, factory = site
    [owner_id, other_id], problem_id = await create_fixture(factory, users=2)
    fake_judge(monkeypatch)
    client.cookies.set("session", login_cookie(owner_id))
    ids = []
    for _ in range(5):
        response = await client.post(f"/api/problems/{problem_id}/submit", json={"language": "python", "code": "solve()"})
        ids.append(response.json()["submission_id"])
    async with factory() as session:
        solved = await session.scalar(select(func.count(UserSolvedProblem.id)).where(UserSolvedProblem.user_id == owner_id))
        assert solved == 1
        accepted = await session.scalar(select(func.count(Submission.id)).where(Submission.user_id == owner_id, Submission.verdict == "Accepted"))
        assert accepted == 5
        rank = await RankingRepository.get_all_time_ranking(session, 10)
        assert [(user.id, count) for user, count in rank] == [(owner_id, 1)]
    board = await client.get("/leaderboard")
    assert '<td>Student 0</td><td>1</td><td>5</td>' in board.text
    assert (await client.get(f"/api/submissions/{ids[0]}/code")).text == "solve()"
    client.cookies.set("session", login_cookie(other_id))
    assert (await client.get(f"/api/submissions/{ids[0]}/code")).status_code == 404


@pytest.mark.asyncio
async def test_hidden_test_case_failure_does_not_leak_input_or_output(site, monkeypatch):
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(user_id))
    fake_judge(monkeypatch)
    created = await client.post(f"/api/problems/{problem_id}/submit", json={"language": "cpp", "code": "HIDDEN_FAIL"})
    result = await client.get(f"/api/submissions/{created.json()['submission_id']}")
    assert result.json()["result"] == "Wrong Answer"
    assert result.json()["failure"] is None
    async with factory() as session:
        row = await session.get(Submission, created.json()["submission_id"])
        assert row.judge_token is None
        assert row.failure_details is None


@pytest.mark.asyncio
async def test_oauth_updates_existing_discord_user_and_returns_to_problem(site, monkeypatch):
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)

    def oauth_response(request):
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "fake-token"})
        if request.url.path.endswith("/@me"):
            return httpx.Response(200, json={"id": str(900000), "username": "updated", "global_name": "Updated Name", "avatar": "avatar-hash"})
        return httpx.Response(404)

    fake_judge(monkeypatch, oauth_response)
    login = await client.get("/auth/login", params={"next": f"/problems/{problem_id}"})
    assert login.status_code == 302
    from urllib.parse import urlparse, parse_qs
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    callback = await client.get("/auth/callback", params={"code": "fake-code", "state": state}, follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == f"/problems/{problem_id}"
    page = await client.get(callback.headers["location"])
    assert page.status_code == 200
    async with factory() as session:
        assert await session.scalar(select(func.count(User.id)).where(User.discord_user_id == 900000)) == 1
        user = await session.scalar(select(User).where(User.discord_user_id == 900000))
        assert user.id == user_id
        assert user.discord_username == "Updated Name"
        assert user.discord_avatar == "avatar-hash"


@pytest.mark.asyncio
async def test_leaderboard_order_matches_shared_solved_rows(site):
    client, factory = site
    [a_id, b_id, c_id], target_problem = await create_fixture(factory, users=3)
    async with factory() as session:
        extra = [Problem(problem_number=900001 + i, title=f"Practice {i}") for i in range(5)]
        session.add_all(extra)
        await session.flush()
        for owner_id, count in ((a_id, 3), (b_id, 2), (c_id, 1)):
            for problem_id in [target_problem, *[problem.id for problem in extra[:count - 1]]]:
                session.add(UserSolvedProblem(user_id=owner_id, problem_id=problem_id, first_accepted_at=datetime.now(timezone.utc)))
        await session.commit()
    async with factory() as session:
        ranking = await RankingRepository.get_all_time_ranking(session, 10)
        assert [(user.id, solved) for user, solved in ranking] == [(a_id, 3), (b_id, 2), (c_id, 1)]
        discord_ranking = await RankingService.get_all_time_ranking_data(session, 10)
        assert [(user.id, solved) for user, solved in discord_ranking] == [(a_id, 3), (b_id, 2), (c_id, 1)]
    client.cookies.set("session", login_cookie(a_id))
    page = await client.get("/leaderboard")
    assert page.status_code == 200
    assert page.text.index("Student 0") < page.text.index("Student 1") < page.text.index("Student 2")


@pytest.mark.asyncio
async def test_daily_discord_buttons_link_to_fixture_problem(site):
    _, factory = site
    _, problem_id = await create_fixture(factory)
    async with factory() as session:
        problem = await session.get(Problem, problem_id)
        view = DailyProblemView(problem)
        links = {child.label: child.url for child in view.children if getattr(child, "url", None)}
        expected = f"{web.settings.WEBSITE_BASE_URL}/problems/{problem_id}"
        assert links["💻 開始作答"] == expected
        assert links["📖 查看題目"] == expected


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_judge0_end_to_end_if_configured(site):
    """Opt-in live test: set JUDGE0_URL (and any required credentials) to run."""
    if os.getenv("RUN_JUDGE0_INTEGRATION") != "1" or not web.settings.JUDGE0_URL:
        pytest.skip("Set RUN_JUDGE0_INTEGRATION=1 and a reachable JUDGE0_URL to opt in")
    web.settings.JUDGE_PROVIDER = "judge0"
    client, factory = site
    [user_id], problem_id = await create_fixture(factory)
    client.cookies.set("session", login_cookie(user_id))
    solutions = {
        "c": '#include <stdio.h>\nint main(){int i,j;while(scanf("%d%d",&i,&j)==2){int a=i<j?i:j,b=i>j?i:j,m=0;for(int n=a;n<=b;n++){int x=n,c=1;while(x!=1){if(x%2)x=3*x+1;else x/=2;c++;}if(c>m)m=c;}printf("%d %d %d\\n",i,j,m);}return 0;}',
        "cpp": '#include <iostream>\n#include <algorithm>\nusing namespace std;int main(){int i,j;while(cin>>i>>j){int m=0;for(int n=min(i,j);n<=max(i,j);n++){int x=n,c=1;while(x!=1){x=x%2?3*x+1:x/2;c++;}m=max(m,c);}cout<<i<<" "<<j<<" "<<m<<"\\n";}return 0;}',
        "python": 'import sys\nfor line in sys.stdin:\n i,j=map(int,line.split()); m=0\n for n in range(min(i,j),max(i,j)+1):\n  x=n;c=1\n  while x!=1: x=3*x+1 if x%2 else x//2;c+=1\n  m=max(m,c)\n print(i,j,m)',
    }
    for language, code in solutions.items():
        created = await client.post(f"/api/problems/{problem_id}/submit", json={"language": language, "code": code})
        result = await client.get(f"/api/submissions/{created.json()['submission_id']}")
        assert result.json()["result"] == "Accepted"
    live_cases = [
        ("cpp", '#include <iostream>\nint main( {', "Compilation Error"),
        ("c", "int main(){return 1;}", "Runtime Error"),
        ("cpp", "int main(){for(;;){} return 0;}", "Time Limit Exceeded"),
        ("python", "print('wrong')", "Wrong Answer"),
    ]
    for language, code, expected in live_cases:
        created = await client.post(f"/api/problems/{problem_id}/submit", json={"language": language, "code": code})
        result = await client.get(f"/api/submissions/{created.json()['submission_id']}")
        assert result.json()["result"] == expected
