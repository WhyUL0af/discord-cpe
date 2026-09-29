# Phase 2–4 交付與驗證

## 完成項目

### Phase 2：Problem

沿用 Problem model、ProblemRepository 與既有 UVa 100 development fixture。
新增 WebsiteProblemService 與 public projection，搜尋題號／題名、難度、source、個人 solved/unsolved。
`GET /api/problems`、`GET /api/problems/{id}` 不輸出 test_cases。
題目 HTML／initial JS 僅包含敘述、sample、limits 與語言 config。
URL 仍使用 database id；UVa 題號 100 不代表 URL id=100。

fixture 不會自動 seed；新增明確執行的 `app.scripts.seed_development`，限制 APP_ENV、資料庫名稱
與確認旗標，且題目已存在時不覆寫 operator 管理的內容。fixture 是自建練習資料，非 UVa 官方 judge data。

### Phase 3：Workspace

Desktop 使用可各自捲動的 Problem／Monaco／Console 工作區，mobile 使用 Problem／Code／Result 切換。
四種語言 config：C++17、C17、Python 3、Java 21；這四種 metadata 已由 Mock 測試。
各語言 starter、Monaco syntax／line numbers／automatic layout、dark/light、鍵盤操作、live result。
localStorage `draft:{user}:{problem}:{language}`，切語言、離頁、refresh 保留草稿。
Monaco CDN 失敗時使用保留相同草稿機制的 textarea；CDN fallback 已做 JavaScript unit test，
本次 browser 未實際阻斷 CDN。

Run Sample／Custom Input 分開選擇；空 custom input 也能明確送出。
Console 顯示 execution result、stdout、stderr，Mock 永遠標示未執行程式。

### Phase 4：Submission

`JudgeProvider.run/submit` 是 provider-neutral async boundary；RunService 與 WebsiteSubmissionService
不認識 Judge0 payload／status IDs。既有 Bot SubmissionService 繼續處理 uHunt；没有重寫 Bot。
既有 Judge0 HTTP 功能移至 Judge0Provider，保留 HTTP mock contract tests，未連真實服務。

MockJudgeProvider 只依 server-side scenario 設定模擬 AC/WA/CE/TLE/MLE/RE/Internal Error，
不分析或執行 source。APP_ENV 預設 production、JUDGE_PROVIDER 預設 disabled。
production 選 mock 時 lifespan fail-fast，provider selection 也拒絕。

Submission DB 狀態 QUEUED → RUNNING → FINISHED，API status 對應 queued/running/finished。
API verdict 使用 ACCEPTED 等 enum；DB 保留 Accepted 等舊 label，讓 Bot 的既有 AC 統計繼續運作。
POST 先 commit queued 後返回，背景任務評測，前端 polling。
保存 started/finished、provider marker、passed/total tests、compiler message。
Mock 計數與 runtime/memory 均為模擬值，不是執行量測。

本人 history/detail API／HTML、source API 都驗證 ownership。payload 禁止額外的 user_id、verdict、
runtime、passed_tests 等欄位；source 上限 256 KiB UTF-8 bytes。
compiler message 以診斷分類白名單縮減／截斷，不回傳原始命令、paths、environment。
service 再確認 failure index 對應公開 case，hidden case 失敗不輸出 input/output。
Only Accepted 建立既有 UserSolvedProblem；savepoint 處理唯一鍵競爭，重複 AC 保持 solved=1。
網站與 Discord Ranking 仍共用 RankingService。

## Migration

新增 `0007_submission_pipeline`，接續 `0006_submission_failure_details`。
新增 status、judge_provider、passed_tests、total_tests、compiler_message、started_at、finished_at。
現有 Bot records 預設 FINISHED；舊 website Pending/Judging 分別 backfill QUEUED/RUNNING。
不 reset、不刪資料、不建立另一套題庫或 user/solved 表。

SQLite migration upgrade/downgrade/re-upgrade 與舊資料保留測試通過；
**未在真實 PostgreSQL／Ubuntu 執行 migration**。
backfill 只保留舊任務狀態，不會自動重新排程舊 Pending/Judging。

## 開發 Mock 操作

在獨立 development env（不要更改 production secrets）設定：

```dotenv
APP_ENV=development
JUDGE_PROVIDER=mock
JUDGE_MOCK_VERDICT=ACCEPTED
JUDGE_MOCK_DELAY_SECONDS=0.3
DATABASE_URL=postgresql+asyncpg://YOUR_DEV_USER:YOUR_DEV_PASSWORD@YOUR_DEV_DB_HOST:5432/cpe_development
```

先自行準備獨立開發資料庫，再執行：

```bash
ENV_FILE=/path/to/development.env alembic upgrade head
ENV_FILE=/path/to/development.env python -m app.scripts.seed_development --confirm-development-database
ENV_FILE=/path/to/development.env uvicorn app.web:app --host 127.0.0.1 --port 8000
```

沿用正常 Discord OAuth 登入。可改 server-side JUDGE_MOCK_VERDICT 並重啟測試不同 verdict。
現有 production Compose 的 DATABASE_URL 仍強制指向 cpe_bot，不要只改 APP_ENV 就拿 production Compose 跑 Mock。
本階段未進行 Ubuntu deployment 或建立 Judge worker。

## API

- Public：GET /api/problems、GET /api/problems/{id}。
- Authenticated：POST /api/run、POST /api/submissions（包含 problem_id/language/code/input/input_mode）。
- 保留 POST /api/problems/{id}/run、POST /api/problems/{id}/submit。
- 本人：GET /api/submissions、GET /api/submissions/{id}、GET /api/submissions/{id}/code。
- HTML：/problems、/problems/{id}、/submissions、/submissions/{id}。
- 外部 origin／Sec-Fetch-Site cross-site mutations 被拒絕；仍使用 Phase 1 OAuth state、HttpOnly／SameSite／HTTPS Secure cookie。

## 實際執行的驗證

Windows 既有專案 venv，沒有修改系統 Python，也沒有連正式 DB。

| Command | 結果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | 94 passed，0 failed，1 skipped |
| `node --test tests/workspace.test.cjs` | 3 passed，0 failed |
| `node --check app/static/workspace.js` | 通過 |
| `.venv/Scripts/python.exe -m compileall -q app tests` | 通過 |
| `git diff --check` | 通過，僅 Git CRLF 提示 |

Skipped 是明確 opt-in real Judge0 integration，依本次需求未執行。
原有測試保留，新增涵蓋 problem projection/filter、四語言 Mock、Run 無 DB side effects、
可觀察狀態、七種 verdict、重複 AC、IDOR／history／API auth、byte limit、untrusted fields、
compiler scrub、production Mock guard、provider hidden-failure defense、seed guard/idempotency、migration 保留資料。
JavaScript unit tests 使用模擬 DOM／Monaco／storage，不等同真 browser；瀏覽器另行驗證如下。
requirements.txt 與 pyproject 的 dev extras 補上既有 SQLite tests 所需 aiosqlite，讓新環境可重現測試。

## Browser verification

使用 in-app Chromium browser，loopback `127.0.0.1:8765`；APP_ENV=test、Mock、
單獨暫存 SQLite `discord_cpe_browser_test_20260929.sqlite3`。
啟動 `tests.browser_fixture_app:app`，test-only session/scenario routes 僅存在測試入口，
正式 `app.web:app` 不含登入繞過／scenario endpoints。沒有做真實 Discord OAuth。

- /problems：fixture 題號、source 與未完成標示可見。
- /problems/1：desktop split layout、Monaco 實際載入。
- Java 21 starter、輸入草稿、切 C++ 再切回、refresh 與離頁再返回均保留。
- Run Sample 與手機 Custom Input：顯示清楚標示的 Mock stdout。
- Submit：Queued／Running Judging 可見，finished Mock AC／WA／CE 結果可見。
- 同一題重複 Mock AC：排名表顯示 Solved=1、Accepted submissions 增加。
- /submissions、/submissions/2：本人 history 與 source/detail 可見。
- 390×844 viewport：Problem／Code／Result 分頁及 light theme 可操作；驗證後 viewport 已 reset。

畫面：

![Desktop Mock Accepted](verification/phase234-desktop.png)
![Mobile editor](verification/phase234-mobile.png)
![Mock Compilation Error](verification/phase234-compilation-error.png)

Browser QA 是 Mock 流程驗證，不能視為真正編譯／安全 sandbox 或 Ubuntu deployment 通過。
QA server 驗證結束後停止。

## 仍待後續

- 真實 Discord OAuth、Judge0／其他 external Judge、PostgreSQL／Docker／Ubuntu 未驗證。
- Java21/C17 真實 compiler 能力仍未驗證；舊 Judge0 adapter 只保留原 C/C++/Python IDs。
- 背景任務沒有 durable queue／重啟恢復（本階段明確不建 worker）。
- 並行唯一鍵處理有 savepoint 防護；沒有真 PostgreSQL concurrency 壓力測試。
- 沒有完整 49 題／官方 hidden cases、Profile（Phase 5）、contest engine、sandbox。
- 可先進行 Phase 5 Profile／統計，之後再選擇並驗證 external Judge 與 deployment。
