"""Phase 1 dashboard and navigation regression tests; no external services."""
from app import web
from app.models import Problem, Submission, UserSolvedProblem
from app.services.dashboard_service import DashboardService
from tests.test_website_judge import site, create_fixture, login_cookie

import pytest


@pytest.mark.asyncio
async def test_dashboard_reuses_progress_and_only_current_users_history(site):
    client, factory = site
    users, problem_id = await create_fixture(factory, users=2)
    async with factory() as session:
        other = Problem(problem_number=272, title="TEX Quotes")
        session.add(other)
        await session.flush()
        session.add_all([
            UserSolvedProblem(user_id=users[0], problem_id=problem_id),
            Submission(user_id=users[0], problem_id=problem_id, verdict="Accepted"),
            Submission(user_id=users[0], problem_id=problem_id, verdict="Accepted"),
            Submission(user_id=users[0], problem_id=other.id, verdict="Wrong Answer"),
            Submission(user_id=users[1], problem_id=problem_id, verdict="PRIVATE_RESULT"),
        ])
        await session.commit()
        data = await DashboardService.get_dashboard(session, users[0])
        assert (data.solved, data.total) == (1, 2)
        assert data.continue_problem.id == other.id
        assert len(data.recent) == 3
        assert data.ranking[0][1] == 1
    client.cookies.set("session", login_cookie(users[0]))
    response = await client.get("/")
    assert response.status_code == 200
    assert "1 / 2" in response.text
    assert "繼續作答" in response.text
    assert "PRIVATE_RESULT" not in response.text
    assert "排行榜摘要" in response.text


@pytest.mark.asyncio
async def test_empty_dashboard_navigation_and_logout(site):
    client, factory = site
    users, _ = await create_fixture(factory)
    public = await client.get("/")
    assert "使用 Discord 登入" in public.text
    client.cookies.set("session", login_cookie(users[0]))
    response = await client.get("/")
    assert "0 / 1" in response.text
    assert "今日題目尚未發布" in response.text
    assert "選擇下一題" in response.text
    assert "action=\"/auth/logout\"" in response.text
    assert (await client.get("/ranking")).text == (await client.get("/leaderboard")).text
    assert "尚未提供網站模擬考" in (await client.get("/contest")).text
    logout = await client.post("/auth/logout")
    assert logout.status_code == 303
    assert "expires=Thu, 01 Jan 1970" in logout.headers["set-cookie"]
    assert "httponly" in logout.headers["set-cookie"]


@pytest.mark.parametrize("target", ["https://evil.example", "//evil.example", "/\\evil.example", "/\ninvalid"])
def test_oauth_return_path_rejects_external_or_control_paths(target):
    assert web.safe_return_path(target) == "/"


def test_oauth_return_path_preserves_problem():
    assert web.safe_return_path("/problems/100?q=1") == "/problems/100?q=1"
