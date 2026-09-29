# Website audit 與 Phase 1

以下是 Phase 1 開始時的 audit。Phase 2–4 的新實作與驗證請見 [Phase 2–4 交付](PHASE234.md)。

## 檢查範圍

README、pyproject.toml、requirements.txt、app/web.py、Bot commands/views/tasks、models、
repositories、services、providers、Alembic 0001–0006、Dockerfile、Compose、部署腳本、
.env.example 與現有 tests。repository 沒有 package.json、獨立 web/ 前端、templates/static。
未讀取或修改 production secrets；保留開始時所有未提交修改。

## 實際現況

| 項目 | 狀態／可沿用內容 |
| --- | --- |
| Frontend | FastAPI route 直接產生 HTML/CSS/JS；Monaco CDN；沒有 React/Vue build |
| Website | /、/problems、/problems/{database id}、/submissions、/leaderboard 已存在 |
| OAuth | identify、state 驗證、signed session；HTTPS Secure、HttpOnly、SameSite=Lax；登入後返回題目 |
| User | discord_user_id 唯一，同一 users table 與 Bot 共用；avatar 已存在 |
| Problem | 題號與 DB id 不同；statement/input/output/sample 欄位、毫秒時限、KB 記憶體、JSON 測資 |
| Samples | 目前單組 sample_input/sample_output，未獨立 SampleTestcase；後續再決定擴充 |
| Hidden cases | test_cases 僅後端使用；公開題目頁不序列化；只回傳 hidden:false 的失敗細節 |
| Submission | code、language、verdict、runtime、memory、failure_details；尚無獨立狀態／測試計數／開始結束時間 |
| Solved | UserSolvedProblem 唯一(user_id, problem_id)，沿用；並行 AC 的競爭條件尚待處理 |
| Ranking | RankingRepository distinct problem，Bot 經 RankingService；網站原本直接呼叫 repository |
| Judge | app/web.py 直接呼叫 Judge0；沒有 JudgeProvider／MockJudgeProvider；現有 mock 是 HTTP 測試 mock |
| Run/Submit | Run 不建提交；Submit Pending → Judging → 結果，以背景任務處理並 polling |
| Bot | 每日一題按鈕已導向 Website；既有 Bot commands／uHunt 追蹤可保留 |
| Fixture | tests/fixtures/uva100_development.json，非官方、development only；不自動 seed |
| Deployment | postgres、website、discord-bot；Judge0 外部提供；migration 於啟動執行 |

## 尚缺功能與限制

- Problem public API、完成狀態篩選、多組 sample：Phase 2。
- 草稿保存、mobile workspace、Java 21／C17 的 provider 能力宣告：Phase 3。
- JudgeProvider、production 禁用 Mock、SubmissionService 與完整狀態、測試計數、
  編譯錯誤清理、MLE/Internal Error：Phase 4。不能把既有 Judge0 C/Java ID 誤稱為 C17/Java21。
- Profile、詳細 submission 頁面：Phase 5。ownership API 已存在但需繼續擴充測試。
- CSRF／Origin 檢查、rate limiting、OAuth 同時建立 User 的競爭條件、來源大小上限、
  背景任務在重啟時的恢復：後續 security／submission 工作；本階段不宣稱 production-ready。
- /problems/{id} 沿用 database primary key；UVa 100 不保證 database id=100。
- Compose 固定名字及 8000 host port、多專案命名、Bot/Website 同時 migration 的風險仍需部署階段处理。
- 沒有真正 Judge0、Discord 授權、Ubuntu PostgreSQL migration 或瀏覽器 QA 的驗證結果。

## 最小改動架構

沿用 SQLAlchemy 與 Bot 資料庫，不建立 WebUser 或另一套 solved/ranking。
逐步把 route 內 business logic 抽至 service；由 repository 查詢、provider 呼叫外部服務。
Phase 1 僅新增 DashboardService → DashboardRepository，OAuth 重用 UserRepository，
網站排名重用 RankingService。Phase 4 再把 Judge0 gateway 抽到 JudgeProvider，保留既有 API 相容性。

## Phase 1 實際變更

- app/web.py：Dashboard／navigation／logout、/ranking alias、/contest 提示頁、OAuth local-return path 驗證。
- app/services/dashboard_service.py：進度、每日題目、續作、最近提交、排名摘要。
- app/repositories/dashboard_repo.py：本人查詢與未解題續作，沿用現有 schema。
- .dockerignore：排除 .env、venv、Git 等，避免 COPY . 收入 secrets。
- tests/test_website_dashboard.py：資料隔離、duplicate AC 統計、空資料、導覽、登出、返回路徑。
- tests/test_website_judge.py：測試自己的簽章 secret 與 HTTPS，不受部署設定 Secure cookie 影響；
  真實 Judge 測試增加 RUN_JUDGE0_INTEGRATION=1 明確 opt-in。
- README.md／本文件：Phase 1 與驗證說明。

沒有新增 migration、修改模型、seed／reset 資料庫、部署 worker 或執行 user code。

## 實際驗證

Windows 專案 venv 執行 `python -m pytest -q`：70 passed、1 skipped。
略過的是 opt-in real Judge0 integration。最初測試發現 Secure cookie 在 HTTP 測試 client 下
不會送出，以及已設定 endpoint 讓 integration 自動觸發；改為 HTTPS 測試及明確 opt-in 後回歸通過。
這是開發測試，不能代表 Ubuntu deployment、真實 OAuth 或 sandbox 驗證。
