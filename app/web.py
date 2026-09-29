"""Discord-authenticated practice website with provider-neutral judge services."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import date, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Submission, User, UserSolvedProblem
from app.repositories.user_repo import UserRepository
from app.services.dashboard_service import DashboardService
from app.services.ranking_service import RankingService
from app.providers.judge_factory import get_judge_provider, validate_judge_configuration
from app.providers.judge_provider import JudgeProvider
from app.repositories.submission_repo import SubmissionRepository
from app.services.website_problem_service import WebsiteProblemService
from app.services.website_judge_service import CodePayload, RunService, WebsiteSubmissionService, submission_data
from app.website_workspace import render_workspace

logger = logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(app):
    validate_judge_configuration()
    yield


app = FastAPI(title="CPE Practice", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.WEBSITE_SESSION_SECRET, same_site="lax", https_only=settings.WEBSITE_BASE_URL.startswith("https://"))
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.middleware("http")
async def same_origin_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != settings.WEBSITE_BASE_URL.rstrip("/")):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "跨站請求遭拒絕"}, status_code=403)
    return await call_next(request)


async def db_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


Db = Annotated[AsyncSession, Depends(db_session)]


async def current_user(request: Request, session: Db) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "請先使用 Discord 登入")
    user = await session.get(User, user_id)
    if not user:
        request.session.clear()
        raise HTTPException(401, "登入已失效，請重新登入")
    return user


UserDep = Annotated[User, Depends(current_user)]
JudgeDep = Annotated[JudgeProvider, Depends(get_judge_provider)]


@app.get("/auth/login")
async def login(request: Request, next: str = Query("/")):
    if not settings.DISCORD_OAUTH_CLIENT_ID or not settings.DISCORD_OAUTH_CLIENT_SECRET:
        raise HTTPException(503, "Discord OAuth 尚未設定")
    if len(settings.WEBSITE_SESSION_SECRET) < 32 or settings.WEBSITE_SESSION_SECRET == "change-this-session-secret":
        raise HTTPException(503, "WEBSITE_SESSION_SECRET 必須設定為至少 32 字元的隨機值")
    next = safe_return_path(next)
    import secrets
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    request.session["return_to"] = next
    params = {"client_id": settings.DISCORD_OAUTH_CLIENT_ID, "redirect_uri": settings.DISCORD_OAUTH_REDIRECT_URI, "response_type": "code", "scope": "identify", "state": state}
    return RedirectResponse("https://discord.com/oauth2/authorize?" + urlencode(params), status_code=302)


@app.get("/auth/callback")
async def oauth_callback(request: Request, session: Db, code: str = "", state: str = "", error: str = ""):
    target = request.session.get("return_to", "/")
    expected = request.session.pop("oauth_state", None)
    if error or not code or not expected or not secrets_compare(state, expected):
        raise HTTPException(400, "Discord 登入失敗或驗證狀態無效")
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post("https://discord.com/api/oauth2/token", data={"client_id": settings.DISCORD_OAUTH_CLIENT_ID, "client_secret": settings.DISCORD_OAUTH_CLIENT_SECRET, "grant_type": "authorization_code", "code": code, "redirect_uri": settings.DISCORD_OAUTH_REDIRECT_URI}, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if token_response.is_error:
            logger.warning("Discord OAuth token exchange failed: %s", token_response.status_code)
            raise HTTPException(502, "無法完成 Discord 登入")
        profile_response = await client.get("https://discord.com/api/users/@me", headers={"Authorization": "Bearer " + token_response.json()["access_token"]})
        if profile_response.is_error:
            raise HTTPException(502, "無法取得 Discord 帳號資訊")
        profile = profile_response.json()
    discord_id = int(profile["id"])
    user = await UserRepository.get_or_create(
        session, discord_id, profile.get("global_name") or profile["username"])
    user.discord_avatar = profile.get("avatar")
    await session.flush()
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(safe_return_path(target), status_code=303)


def safe_return_path(target: str) -> str:
    """Allow only local paths, including after browser backslash normalization."""
    if not target.startswith("/") or target.startswith("//") or "\\" in target or any(ord(c) < 32 for c in target):
        return "/"
    return target


def secrets_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)


@app.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


def page_shell(title: str, body: str, user: User | None = None) -> HTMLResponse:
    auth = (f'<span>{html_escape(user.discord_username or "Discord User")}</span><img class="avatar" src="https://cdn.discordapp.com/avatars/{user.discord_user_id}/{user.discord_avatar}.png?size=64" alt="">' if user and user.discord_avatar else f'<span>{html_escape(user.discord_username or "Discord User")}</span>' if user else '<a class="button" href="/auth/login">Discord 登入</a>')
    if user:
        auth += '<form method="post" action="/auth/logout"><button type="submit">登出</button></form>'
    if settings.JUDGE_PROVIDER == "mock":
        body = '<p class="mock-notice" role="note">Development Mock Judge：不執行程式碼，所有結果與解題進度均為開發模擬。</p>' + body
    html = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html_escape(title)} · CPE</title><script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.52.2/min/vs/loader.js"></script><style>
    :root{{color-scheme:dark;--bg:#101217;--panel:#171a21;--line:#2a2e38;--text:#e8eaf0;--muted:#9aa2b1;--accent:#a6e3a1}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif}}header{{height:64px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 max(24px,calc((100% - 1200px)/2));position:sticky;top:0;background:#101217ed;z-index:3}}nav{{display:flex;gap:16px;flex-wrap:wrap}}a{{color:inherit;text-decoration:none}}a:hover{{color:var(--accent)}}.brand{{font-weight:750;font-size:19px;margin-right:32px}}.right{{display:flex;align-items:center;gap:10px}}.avatar{{width:32px;height:32px;border-radius:50%}}main{{max-width:1200px;margin:36px auto;padding:0 24px}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:22px;margin:14px 0}}.muted{{color:var(--muted)}}.button,button,select,input{{background:#252a34;color:var(--text);border:1px solid #383e4a;border-radius:7px;padding:9px 14px;font:inherit}}.button,button{{cursor:pointer}}button.primary,.primary{{background:#b5e8ac;color:#101810;border:0;font-weight:700}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;border-bottom:1px solid var(--line);text-align:left}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}pre{{white-space:pre-wrap;background:#101217;padding:14px;border-radius:6px;overflow:auto}}#editor{{height:62vh;border:1px solid var(--line)}}.actions{{display:flex;gap:10px;align-items:center;margin:12px 0}}textarea{{width:100%;min-height:100px;background:#101217;color:var(--text);border:1px solid var(--line);padding:10px;border-radius:6px}}.error{{color:#ff8a8a}}@media(max-width:800px){{header{{padding:8px 12px;height:auto;min-height:64px;flex-wrap:wrap;gap:8px}}nav{{gap:10px;font-size:13px}}.brand{{margin-right:6px}}main{{padding:0 14px}}.cols{{grid-template-columns:1fr}}#editor{{height:48vh}}}}</style><link rel="stylesheet" href="/static/workspace.css"></head><body><header><div class="right"><a class="brand" href="/">CPE</a><nav><a href="/">Dashboard</a><a href="/problems">題庫</a><a href="/submissions">提交紀錄</a><a href="/ranking">排行榜</a><a href="/contest">模擬考</a></nav></div><div class="right">{auth}</div></header><main>{body}</main></body></html>'''
    return HTMLResponse(html)


def html_escape(value: str) -> str:
    import html
    return html.escape(value)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session: Db):
    user = await get_optional_user(request, session)
    if not user:
        return page_shell("CPE 練習", '<h1>每天練一題，穩定向前</h1><p class="muted">使用 Discord 帳號登入，接續你的 CPE 練習。</p><a class="button primary" href="/auth/login">使用 Discord 登入</a><div class="panel"><h2>題庫</h2><a href="/problems">瀏覽 UVa 題目 →</a></div>')
    data = await DashboardService.get_dashboard(session, user.id)
    daily_html = f'<a class="button primary" href="/problems/{data.daily.id}">開始今日題目 · UVa {data.daily.problem_number}</a>' if data.daily else '<p class="muted">今日題目尚未發布</p>'
    continue_html = f'<a class="button" href="/problems/{data.continue_problem.id}">繼續作答 · {html_escape(data.continue_problem.title)}</a>' if data.continue_problem else '<a class="button" href="/problems">選擇下一題</a>'
    rows = ''.join(f'<tr><td>{sub.submitted_at:%m/%d %H:%M}</td><td><a href="/problems/{sub.problem.id}">{html_escape(sub.problem.title)}</a></td><td>{html_escape(sub.verdict)}</td></tr>' for sub in data.recent) or '<tr><td colspan="3" class="muted">還沒有提交紀錄</td></tr>'
    ranking = ''.join(f'<tr><td>{i}</td><td>{html_escape(person.discord_username or "Discord User")}</td><td>{count}</td></tr>' for i, (person, count) in enumerate(data.ranking, 1)) or '<tr><td colspan="3">目前沒有解題紀錄</td></tr>'
    return page_shell("首頁", f'<h1>嗨，{html_escape(user.discord_username or "同學")}</h1><section class="panel"><h2>🎯 今日題目</h2>{daily_html}</section><div class="cols"><section class="panel"><h2>練習進度</h2><p>完成題數　<strong>{data.solved} / {data.total}</strong></p>{continue_html}</section><section class="panel"><h2>最近提交紀錄</h2><table><thead><tr><th>時間</th><th>題目</th><th>結果</th></tr></thead><tbody>{rows}</tbody></table></section></div><section class="panel"><h2>排行榜摘要</h2><table><thead><tr><th>排名</th><th>使用者</th><th>Solved</th></tr></thead><tbody>{ranking}</tbody></table><a href="/ranking">查看排行榜 →</a></section>', user)


async def get_optional_user(request: Request, session: AsyncSession):
    uid = request.session.get("user_id")
    return await session.get(User, uid) if uid else None


async def streak_for(session: AsyncSession, user_id: int) -> int:
    dates = (await session.scalars(select(func.date(UserSolvedProblem.first_accepted_at)).where(UserSolvedProblem.user_id == user_id).order_by(func.date(UserSolvedProblem.first_accepted_at).desc()))).all()
    unique = list(dict.fromkeys(dates))
    if not unique:
        return 0
    today = date.today()
    first = unique[0]
    if isinstance(first, str):
        first = date.fromisoformat(first)
    if first < today - timedelta(days=1):
        return 0
    expected = first
    streak = 0
    for item in unique:
        day = date.fromisoformat(item) if isinstance(item, str) else item
        if day == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif day < expected:
            break
    return streak


@app.get("/api/problems")
async def problems_api(request: Request, session: Db, q: str = "", difficulty: str = "", solved: str = "", category: str = ""):
    user = await get_optional_user(request, session)
    return await WebsiteProblemService.search(session, user.id if user else None, q=q, difficulty=difficulty, solved=solved, category=category)


@app.get("/api/problems/{problem_id}")
async def problem_api(problem_id: int, session: Db):
    from app.services.website_problem_service import public_problem
    return public_problem(await WebsiteProblemService.get(session, problem_id))


@app.get("/problems", response_class=HTMLResponse)
async def problems_page(request: Request, session: Db, q: str = "", difficulty: str = "", solved: str = "", category: str = ""):
    user = await get_optional_user(request, session)
    items = await WebsiteProblemService.search(session, user.id if user else None, q=q, difficulty=difficulty, solved=solved, category=category)
    rows = ''.join(f'<tr><td>{"✓" if p["solved"] else "—"}</td><td>{p["problem_number"]}</td><td><a href="/problems/{p["id"]}">{html_escape(p["title"])}</a></td><td>{html_escape(p["difficulty"] or "未標註")}</td><td>{html_escape(p["source"])}</td></tr>' for p in items)
    choices = ''.join(f'<option value="{value}" {"selected" if solved == value else ""}>{label}</option>' for value, label in (("", "全部"), ("solved", "已完成"), ("unsolved", "未完成")))
    return page_shell("題庫", f'<h1>CPE 題庫</h1><form class="actions"><label>搜尋 <input name="q" placeholder="題號或題名" value="{html_escape(q)}"></label><label>難度 <input name="difficulty" placeholder="例如 ⭐" value="{html_escape(difficulty)}"></label><label>完成狀態 <select name="solved">{choices}</select></label><button>篩選</button></form><div class="table-scroll"><table><thead><tr><th>狀態</th><th>題號</th><th>題名</th><th>難度</th><th>Source</th></tr></thead><tbody>{rows or "<tr><td colspan=5>沒有符合條件的題目</td></tr>"}</tbody></table></div>', user)


@app.get("/problems/{problem_id}", response_class=HTMLResponse)
async def problem_page(problem_id: int, request: Request, session: Db):
    problem = await WebsiteProblemService.get(session, problem_id)
    user = await get_optional_user(request, session)
    if not user:
        return RedirectResponse("/auth/login?" + urlencode({"next": f"/problems/{problem_id}"}), status_code=303)
    return page_shell(problem.title, render_workspace(problem, user.id), user)


class SubmissionPayload(CodePayload):
    problem_id: int = Field(gt=0)


@app.post("/api/run")
async def run_api(payload: SubmissionPayload, session: Db, user: UserDep, provider: JudgeDep):
    return await RunService.run(session, payload.problem_id, payload, provider)


@app.post("/api/problems/{problem_id}/run")
async def run_sample(problem_id: int, payload: CodePayload, session: Db, user: UserDep, provider: JudgeDep):
    return await RunService.run(session, problem_id, payload, provider)


async def queue_submission(problem_id, payload, background_tasks, session, user, provider):
    row, request, cases = await WebsiteSubmissionService.create(session, user.id, problem_id, payload, provider)
    background_tasks.add_task(WebsiteSubmissionService.process, AsyncSessionLocal, row.id, request, cases, provider)
    return {"submission_id": row.id, "status": "queued", "result": "Pending", "mock": provider.development_only,
            "language": row.language, "message": "提交已排入佇列。"}


@app.post("/api/submissions")
async def submit_api(payload: SubmissionPayload, background_tasks: BackgroundTasks, session: Db, user: UserDep, provider: JudgeDep):
    return await queue_submission(payload.problem_id, payload, background_tasks, session, user, provider)


@app.post("/api/problems/{problem_id}/submit")
async def submit_code(problem_id: int, payload: CodePayload, background_tasks: BackgroundTasks, session: Db, user: UserDep, provider: JudgeDep):
    return await queue_submission(problem_id, payload, background_tasks, session, user, provider)


@app.get("/api/submissions")
async def submissions_api(session: Db, user: UserDep):
    return [submission_data(row) for row in await SubmissionRepository.list_owned(session, user.id)]


@app.get("/api/submissions/{submission_id}")
async def submission_result(submission_id: int, session: Db, user: UserDep):
    row = await WebsiteSubmissionService.owned(session, submission_id, user.id)
    return submission_data(row, include_code=True)


@app.get("/api/submissions/{submission_id}/code")
async def submission_code(submission_id: int, session: Db, user: UserDep):
    row = await WebsiteSubmissionService.owned(session, submission_id, user.id)
    return PlainTextResponse(row.code or "")


@app.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request, session: Db):
    user = await get_optional_user(request, session)
    if not user:
        return RedirectResponse("/auth/login?next=/submissions", status_code=303)
    items = await SubmissionRepository.list_owned(session, user.id)
    rows = ''.join(f'<tr><td><a href="/submissions/{s.id}">{html_escape(s.verdict)}{" (Mock)" if s.judge_provider == "mock" else ""}</a></td><td><a href="/problems/{s.problem_id}">{html_escape(s.problem.title)}</a></td><td>{html_escape(s.language or "uHunt")}</td><td>{s.runtime if s.runtime is not None else "—"}</td><td>{s.memory if s.memory is not None else "—"}</td><td>{s.submitted_at:%Y-%m-%d %H:%M}</td></tr>' for s in items)
    return page_shell("提交紀錄", '<h1>我的提交紀錄</h1><div class="table-scroll"><table><thead><tr><th>Verdict</th><th>Problem</th><th>Language</th><th>Runtime (ms)</th><th>Memory (KB)</th><th>Submitted At</th></tr></thead><tbody>'+ (rows or '<tr><td colspan="6">還沒有提交紀錄</td></tr>')+'</tbody></table></div>', user)


@app.get("/submissions/{submission_id}", response_class=HTMLResponse)
async def submission_page(submission_id: int, request: Request, session: Db):
    user = await get_optional_user(request, session)
    if not user:
        return RedirectResponse("/auth/login?" + urlencode({"next": f"/submissions/{submission_id}"}), status_code=303)
    row = await WebsiteSubmissionService.owned(session, submission_id, user.id)
    data = submission_data(row, include_code=True)
    mock = '<p class="mock-notice">Development Mock：程式未執行，結果為模擬。</p>' if data["mock"] else ''
    return page_shell("提交詳情", f'<h1>{html_escape(row.verdict)}</h1>{mock}<p>Status: {html_escape(data["status"])} · Language: {html_escape(row.language or "")}</p><p>Runtime: {row.runtime} ms · Memory: {row.memory} KB · Passed Tests: {row.passed_tests} / {row.total_tests}</p><p>Submitted At: {row.submitted_at.isoformat()}</p><h2>Compiler message</h2><pre>{html_escape(data["compiler_message"])}</pre><h2>Source code</h2><pre class="submission-code">{html_escape(row.code or "")}</pre><a href="/submissions">返回提交紀錄</a>', user)


@app.get("/ranking", response_class=HTMLResponse)
@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request, session: Db):
    user = await get_optional_user(request, session)
    ranking = await RankingService.get_all_time_ranking_data(session, 100)
    row_items = []
    for i, (ranked_user, count) in enumerate(ranking, 1):
        accepted = await accepted_count(session, ranked_user.id)
        row_items.append(f'<tr><td>{i}</td><td>{html_escape(ranked_user.discord_username or "Discord User")}</td><td>{count}</td><td>{accepted}</td><td>—</td></tr>')
    rows = ''.join(row_items)
    return page_shell("排行榜", '<h1>完整排行榜</h1><section class="panel"><table><thead><tr><th>Rank</th><th>Discord User</th><th>Solved</th><th>Accepted</th><th>Streak</th></tr></thead><tbody>'+ (rows or '<tr><td colspan="5">目前沒有解題紀錄</td></tr>')+'</tbody></table><p class="muted">計分沿用 Bot 的共同解題紀錄；尚未連續解題資料遷移。</p></section>', user)


async def accepted_count(session: AsyncSession, user_id: int):
    return await session.scalar(select(func.count(Submission.id)).where(Submission.user_id == user_id, Submission.verdict == "Accepted")) or 0


@app.get("/contest", response_class=HTMLResponse)
async def contest_page(request: Request, session: Db):
    user = await get_optional_user(request, session)
    return page_shell("模擬考", '<h1>模擬考</h1><p class="muted">目前尚未提供網站模擬考。可先到題庫練習，或留意 Discord 模擬考公告。</p><a class="button" href="/problems">前往題庫</a>', user)
