# CPE Discord Bot

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-blueviolet.svg)](https://github.com/Rapptz/discord.py)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)

**CPE Discord 通知機器人**：每天發送每日一題，並可用 `/mock_exam` 發送由易到難的 7 題模擬考。成員自行到 UVa Online Judge 提交程式碼，Bot 透過 uHunt 追蹤結果並更新排行榜。

目前部署與選題規則請先閱讀 [通知模式說明](docs/NOTIFICATION_MODE.md)。Ubuntu 採與 OSV 相同的 releases/current 發布方式，完整指令見 [Ubuntu 部署手冊](DEPLOY_UBUNTU.md)。預設 Compose 只啟動 PostgreSQL 與 Bot；網站是停用的可選 profile。沒有新增資料模型或 migration。

頻道用途、權限與可直接貼上的文案見 [Discord 頻道配置](docs/DISCORD_CHANNELS.md)。提交結果改由按鈕取得頻道內私人回覆，不發私訊。

> [!IMPORTANT]
> **非評判系統聲明 (No Custom Judge Policy)**：
> 通知模式由 **UVa Online Judge** 執行評測，Bot 只用公開 uHunt API 取得結果。既有網站與 Judge0 程式碼保留，但不參與預設通知流程。

---

## 目錄

1. [專案架構 (Architecture)](#1-專案架構-architecture)
2. [環境需求 (Requirements)](#2-環境需求-requirements)
3. [Discord Bot 建立與 Developer Portal 設定](#3-discord-bot-建立與-developer-portal-設定)
4. [Bot 權限與邀請連結 (Permissions & Invite)](#4-bot-權限與邀請連結-permissions--invite)
5. [環境變數設定 (.env)](#5-環境變數設定-env)
6. [PostgreSQL 資料庫與 Migration](#6-postgresql-資料庫與-migration)
7. [快速開始 (Docker Compose / 本地執行)](#7-快速開始-docker-compose--本地執行)
8. [Discord Server 頻道與管理員設定 (/setup)](#8-discord-server-頻道與管理員設定-setup)
9. [Slash Commands 指令全覽](#9-slash-commands-指令全覽)
10. [UVa 帳號綁定機制 (/link)](#10-uva-帳號綁定機制-link)
11. [Submission Tracking 追蹤原理](#11-submission-tracking-追蹤原理)
12. [每日一題與選題機制 (Daily Problem)](#12-每日一題與選題機制-daily-problem)
13. [排行榜統計與常駐訊息 (Leaderboard)](#13-排行榜統計與常駐訊息-leaderboard)
14. [常見問題與疑難排解 (Troubleshooting)](#14-常見問題與疑難排解-troubleshooting)
15. [CPE 練習網站](#15-cpe-練習網站)

---

## 1. 專案架構 (Architecture)

本專案遵循嚴格的**分層架構 (Layered Architecture)**，各模組職責分明，方便後續抽換資料來源或擴充指令：

```
cpe-discord-bot/
├── app/
│   ├── config.py                 # Pydantic 類型化環境設定
│   ├── database.py               # Async SQLAlchemy Engine & SessionLocal
│   ├── bot/
│   │   ├── client.py             # Discord.py CpeBot 核心客戶端
│   │   ├── commands/             # Slash Commands (Setup, Account, Problem, Rank)
│   │   ├── views/                # Discord UI Components (Buttons, Embeds)
│   │   └── events/               # 全域錯誤捕捉與日誌事件
│   ├── models/                   # PostgreSQL 資料模型 (SQLAlchemy ORM)
│   ├── repositories/             # 資料存取層 (Data Access Layer)
│   ├── providers/                # 外部 API 抽象 (uHunt API, CPE 題庫)
│   ├── services/                 # 業務邏輯層 (User, Problem, Submission, Daily, Rank)
│   ├── tasks/                    # 非同步背景定時排程 (Tracker, Daily, Ranking)
│   └── data/
│       └── cpe_problems.json     # 官方/歷屆 CPE 題庫資料集 (真實難度標註)
├── alembic/                      # Alembic 資料庫遷移腳本
├── tests/                        # Pytest 單元與整合測試套件
├── Dockerfile                    # 容器建置腳本
├── docker-compose.yml            # Bot + PostgreSQL 容器編排
├── pyproject.toml                # 專案套件管理配置
└── requirements.txt              # 核心依賴套件列表
```

---

## 2. 環境需求 (Requirements)

- **Python**: `3.11+`（已於 Python 3.12 與 3.14 環境驗證相容）
- **PostgreSQL**: `14+`（推薦使用 PostgreSQL 16）
- **Docker & Docker Compose**（若採用容器化部署）
- **Discord 機器人權限**（具有建立 Thread、管理訊息與使用 Slash Commands 權限）

---

## 3. Discord Bot 建立與 Developer Portal 設定

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)。
2. 點擊右上角 **New Application**，輸入機器人名稱（例如 `CPE Assistant`）並建立。
3. 進入左側選單 **Bot** 頁籤：
   - 點擊 **Reset Token** 產生並複製 Token（妥善保存，切勿公開）。
   - **Privileged Gateway Intents**：
     - 本專案主要使用 Slash Commands，預設只需開啟基本 Intents。
     - 若未來需要文字頻道內容偵測，可視需求開啟 Message Content Intent。
4. 儲存變更。

---

## 4. Bot 權限與邀請連結 (Permissions & Invite)

1. 在 Developer Portal 左側前往 **OAuth2** -> **URL Generator**。
2. **SCOPES** 勾選：
   - `bot`
   - `applications.commands`
3. **BOT PERMISSIONS** 勾選以下必要權限：
   - **Send Messages** (發送訊息)
   - **Embed Links** (嵌入連結)
   - **Attach Files** (附加檔案)
   - **Read Message History** (讀取訊息歷史)
   - **Create Public Threads** (建立公開討論串)
   - **Send Messages in Threads** (在討論串中發送訊息)
   - **Manage Threads** (管理討論串 - 用於改名與封存)
   - **Use Slash Commands** (使用應用程式指令)
4. 複製下方產生的 URL，貼入瀏覽器將 Bot 邀請進你的 Discord 伺服器。

---

## 5. 環境變數設定 (.env)

複製範本檔案建立 `.env`：

```bash
cp .env.example .env
```

編輯 `.env` 中的參數：

| 變數名稱 | 說明 | 預設值 / 範例 |
|---|---|---|
| `DISCORD_TOKEN` | Discord Bot Token | `MTAx...` (必填) |
| `DATABASE_URL` | PostgreSQL Async 連線字串 | `postgresql+asyncpg://postgres:password@localhost:5432/cpe_bot` |
| `UHUNT_BASE_URL` | uHunt API 基礎網址 | `https://uhunt.onlinejudge.org/api` |
| `UHUNT_TIMEOUT_SECONDS` | API 請求逾時秒數 | `10.0` |
| `SUBMISSION_POLL_INTERVAL` | 追蹤中的 Active Session 輪詢間隔 (秒) | `20` |
| `DAILY_REPEAT_COOLDOWN_DAYS` | 每日一題避免重複抽題冷卻天數 | `30` |
| `AUTO_ARCHIVE_THREAD` | 解題成功 (AC) 後是否自動封存 Thread | `false` |
| `LOG_LEVEL` | 記錄等級 (DEBUG, INFO, WARNING, ERROR) | `INFO` |

---

## 6. PostgreSQL 資料庫與 Migration

### 資料庫綱要 (Schema)
系統包含以下關鍵資料表：
- `users`: Discord User ID、UVa Username 與 uHunt UID 綁定紀錄。
- `problems`: UVa / CPE 題目資訊（題號、標題、真實星級難度、時間限制、外部題目連結）。
- `active_problem_sessions`: 使用者目前進行中的作答 Thread、開始時間、最後追蹤之 submission_id 與狀態。
- `submissions`: 經 uHunt 取得並儲存的真實提交紀錄與 Verdict。
- `user_solved_problems`: 成員歷史解題紀錄（針對 `(user_id, problem_id)` 設有 UNIQUE 約束，同一題重複 AC 僅算 1 題）。
- `daily_problems`: 每日一題歷史，確保重啟不重複選題。
- `guild_settings`: 多伺服器設定（記錄各伺服器的專屬頻道 ID 與常駐排行榜 Message ID）。

### 執行遷移 (Alembic)
```bash
# 升級至最新版本
alembic upgrade head
```

---

## 7. 快速開始 (Docker Compose / 本地執行)

### 方法 A：使用 Docker Compose（推薦生產部署）

> [!TIP]
> Ubuntu 正式更新使用 `sudo bash /opt/discord-cpe/current/deploy.sh main`，每次建立新版本及備份，再切換 current。舊腳本的首次更新入口見 [Ubuntu 部署手冊](DEPLOY_UBUNTU.md)。以下 Compose 指令適用於已選定的版本。

1. 在 `/etc/discord-cpe/.env` 設定 `DISCORD_TOKEN`、`POSTGRES_PASSWORD` 與資料庫連線；參考 [通知模式說明](docs/NOTIFICATION_MODE.md)。
2. 執行啟動指令：
   ```bash
   docker compose --env-file /etc/discord-cpe/.env up -d --build postgres discord-bot
   ```
3. 查看即時日誌：
   ```bash
   docker compose --env-file /etc/discord-cpe/.env logs -f discord-bot
   ```

### 方法 B：本地虛擬環境執行

1. 建立虛擬環境並安裝依賴：
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```
2. 設定資料庫並執行 Migration：
   ```bash
   alembic upgrade head
   ```
3. 啟動機器人：
   ```bash
   python main.py
   ```

---

## 8. Discord Server 頻道與管理員設定 (/setup)

推薦在 Discord 伺服器建立以下分類與頻道結構：

```
📂 CPE
├── 📢・cpe公告
├── 🎯・每日一題
├── 💻・刷題區
├── 🏆・排行榜
├── 🏁・模擬考
└── 💬・討論區
```

### 建議 💻・刷題區 權限設定

為了維持刷題區乾淨且保有個人隱私，推薦設定如下：

- **@everyone**：
  - 檢視頻道 (View Channel)：`允許 (Allow)`
  - 讀取訊息歷史 (Read Message History)：`允許 (Allow)`
  - 發送訊息 (Send Messages)：`拒絕 (Deny)`（一般成員無法隨意聊天洗頻）
  - 建立公開/私人討論串 (Create Public/Private Threads)：`拒絕 (Deny)`
  - 使用應用程式指令 (Use Application Commands)：`允許 (Allow)`
- **CPE Bot**：
  - 檢視頻道 (View Channel)：`允許 (Allow)`
  - 發送訊息 (Send Messages)：`允許 (Allow)`
  - 嵌入連結 (Embed Links)：`允許 (Allow)`
  - 讀取訊息歷史 (Read Message History)：`允許 (Allow)`

> [!NOTE]
> 💻・自主練習由所有成員共用，常駐互動面板。抽題與解題紀錄以 **私人回覆 (Ephemeral)** 顯示；提交後點「查看提交結果」查詢，不發私訊。需要討論時，請前往 **💬・解題討論**。

加入伺服器後，具有**管理員權限**的成員執行 `/setup` 綁定頻道：

```
/setup daily_channel:#🎯・每日一題 practice_channel:#💻・刷題區 ranking_channel:#🏆・排行榜 discussion_channel:#💬・題目討論
```

- **刷題區**：設定後 Bot 會自動在此建立或維護常駐的「💻 CPE 刷題中心」訊息，重啟時會自動檢查並沿用（edit/reuse），被刪除則自動補建。
- **每日一題頻道**：每天固定時間發布一則挑戰題，並提供快捷作答按鈕。
- **排行榜頻道**：Bot 會發送一則常駐排行榜訊息，日後透過 `message.edit()` 自動更新，不洗頻。

---

## 9. Slash Commands 指令全覽

所有個人相關查詢與操作均使用 **Ephemeral（僅本人可見）** 回覆：

| 指令 | 說明 | 隱私模式 |
|---|---|---|
| `/setup` | 設定伺服器各專用頻道（僅管理員可用） | Ephemeral |
| `/practice_center` | 手動重新發布或維護「CPE 刷題中心」常駐訊息（僅管理員可用） | Ephemeral |
| `/link <uva_username>` | 驗證並綁定個人 UVa 帳號 | Ephemeral |
| `/unlink` | 解除目前 Discord 帳號所綁定的 UVa 帳號 | Ephemeral |
| `/profile [member]` | 查詢 UVa 解題數、提交數與世界排名數據 | Ephemeral / 公開 |
| `/cpe random` | 隨機抽取一題 CPE 題目 | **Ephemeral (僅本人可見)** |
| `/cpe easy` | 隨機抽取一題 CPE 一星精選題目（⭐） | **Ephemeral (僅本人可見)** |
| `/cpe problem <num>` | 指定 UVa 題號取得題目卡片 | **Ephemeral (僅本人可見)** |
| `/mock_exam` | 在目前文字頻道發送 CPE 風格 7 題模擬考（需要管理訊息權限） | 公開通知、私人確認 |
| `/cpe solved` (或 `/solved`) | 檢視個人已完成題目總數與清單 | **Ephemeral (僅本人可見)** |
| `/rank weekly`, `/rank all` | 查詢本週或歷史解題排行榜 | 公開 Embed |
| `/profile [member]` | 查看個人或指定成員的 UVa 解題與提交統計數據 | `/profile` 或 `/profile member:@Alex` |
| `/problem random` | 隨機取得一題 CPE 題目 | `/problem random` |
| `/problem number <num>` | 根據題號精準取得題目 | `/problem number 100` |
| `/problem easy` | 隨機取得一題 CPE 一星常考題（⭐） | `/problem easy` |
| `/solved [member]` | 列出個人或成員目前已解出的 CPE 題目清單 | `/solved` |
| `/rank [scope]` | 檢視排行榜（`weekly` 本週排名 或 `all` 歷史總排名） | `/rank weekly` |

---

## 10. UVa 帳號綁定機制 (/link)

```
Discord User (@Shen)
  └─► 輸入 /link WhyUL0af
        └─► 呼叫 uHunt API (uname2uid/WhyUL0af)
              ├─► 找到 User ID (例如: 123456)
              │     └─► 寫入資料庫 users 表 ──► 回傳 ✅ 綁定成功 Embed
              └─► 回傳 0 或找不到
                    └─► 回傳 ❌ 找不到 UVa User：WhyUL0af（不建立錯誤綁定）
```

- 綁定後，資料庫會儲存該成員的 `discord_user_id`、`uva_username` 及 `uva_user_id`。
- 解除綁定請使用 `/unlink`。
- 使用 `/profile` 可即時從 uHunt 取得公開戰績（Solved、Submissions、AC Rate、World Rank），絕不偽造數據。

---

## 11. Submission Tracking 追蹤原理

系統每隔 `SUBMISSION_POLL_INTERVAL` 秒輪詢所有已綁定 UVa 的成員，僅查資料庫已知題目的提交。使用者可同時解多題，不必建立單題 session 或 Thread。

- 首次同步、重啟及題庫變動時會補入歷史紀錄，不主動發通知。
- 後續使用提交 ID 增量輪詢；In Queue 等未完成結果會重新查詢並回寫同一筆 submission。
- 背景同步 AC、WA、TLE、CE、RE 等結果；點「查看提交結果」取得只有本人可見的回覆，不發私訊。
- 外部提交 ID 去重；網站及 Mock 提交不納入 Discord 排行榜。
- 詳細同步範圍、失敗處理與人工檢查流程見 [通知模式說明](docs/NOTIFICATION_MODE.md)。

---

## 12. 每日一題與選題機制 (Daily Problem)

- 每日一題由背景排程自動選出，排程器會排除最近 `DAILY_REPEAT_COOLDOWN_DAYS`（預設 30 天）內出現過的題目。
- 每日一題於台灣時間（Asia/Taipei）每天早上 07:00 發布；若 Bot 在當天 07:00 後才啟動，會補發尚未發布的當日題目。
- 每日一題會寫入資料庫 `daily_problems` 表，因此 **Bot 重啟後絕對不會重新抽題**。
- 題目卡片包含：
  - `[📖 查看題目]`：直連官方題目 PDF / 說明頁。
  - `[🌐 前往 UVa 提交]`：開啟 UVa Online Judge，由使用者選題及提交。
  - `[🔄 查看提交結果]`：只顯示點擊者在本題已同步的提交結果。
  - `[📊 查看統計]`：即時查詢今日有哪些成員已 AC 本題。

---

## 13. 排行榜統計與常駐訊息 (Leaderboard)

- **去重計分規則**：排名嚴格以 **Solved Problems (不重複解出題目數)** 為主，同一題即使提交 AC 10 次，也僅計為 1 題。
- **資料來源**：只計 `source=uhunt` 且具有外部提交 ID 的 Accepted。週榜依每題最早外部 AC 是否在本週（UTC）計分；網站 Mock 成績不計分。
- **即時更新機制**：Bot 定時透過 `message.edit()` 刷新常駐排行榜訊息，包含：
  - 前十名榜單（附金、銀、銅牌勳章與 UVa 帳號）
  - 本週伺服器總 Submissions 與 Accepted 統計
- 支援 `/rank weekly`（本週解題榜）與 `/rank all`（歷史總榜）。

---

## 14. 常見問題與疑難排解 (Troubleshooting)

### Q1: 如何讓 Bot 追蹤我的結果？
在任意頻道執行 `/link <你的UVa帳號>`，等待首次同步後，自行到 UVa 提交題庫中的題目。

### Q2: 在 UVa 提交程式碼後，沒有看到結果？
1. Bot 不發私訊。確認已綁定帳號、提交題目在 Bot 題庫中，再點「查看提交結果」。
2. UVa / uHunt 本身可能偶有數秒至數十秒的評判延遲，預設輪詢間隔為 20 秒，請稍候。
3. 檢查 Bot 日誌是否出現 `uHunt API timeout` 或連線異常。

### Q3: 機器人重啟後是否會繼續追蹤？
會，Bot 從資料庫讀取已綁定帳號，補入已知題庫的歷史紀錄後繼續輪詢。使用者點按鈕查詢結果，外部提交 ID 不重複計分。

### Q4: 如何執行單元測試？
既有測試包含記憶體資料庫 (aiosqlite) 與模擬外部 API；本次通知模式改動尚未執行 pytest，舊 session／網站共用計分測試需依新需求調整。測試指令：
```bash
pytest -v
```

---

## 15. CPE 練習網站（保留的舊階段文件）

以下是先前網站階段的操作文件。目前通知部署不啟動網站，不需要 Discord OAuth、網域或 Judge0；Discord 排行榜已改為只採外部 uHunt Accepted。手動啟動網站須明確加入 `--profile website`。

網站與 Bot 共用 PostgreSQL；網站 Judge 提交以 `source=website` 區分。這些網站評測結果不計入目前 Discord 的排行榜、已解清單與每日解題統計。

### Discord OAuth 設定

在 Discord Developer Portal 的 OAuth2 設定新增 Redirect URL，必須與 `DISCORD_OAUTH_REDIRECT_URI` 完全一致，例如 `https://cpe.example.edu/auth/callback`。在部署 secrets 設定：

- `WEBSITE_BASE_URL`：網站公開 HTTPS 網址；正式環境用 HTTPS，session cookie 會自動設為 Secure。
- `WEBSITE_SESSION_SECRET`：長且隨機的 session 簽章密鑰。
- `DISCORD_OAUTH_CLIENT_ID`、`DISCORD_OAUTH_CLIENT_SECRET`：OAuth2 應用程式憑證。
- `DISCORD_OAUTH_REDIRECT_URI`：OAuth2 callback URL。

OAuth scope 僅要求 `identify`。Bot 每日題目的「開始作答」與「查看題目」連到 `/problems/{problem.id}`；未登入時會登入後回到該題。

### 網站啟動

本機完成 `.env` 設定及 `alembic upgrade head` 後：

```bash
uvicorn app.web:app --reload --port 8000
```

舊網站需明確執行 `docker compose --env-file /etc/discord-cpe/.env --profile website up -d --build`。Compose 的 PostgreSQL 密碼由 `POSTGRES_PASSWORD` 提供；網站在容器啟動時先執行 migration，再啟動 Uvicorn，並只將 8000 綁定到 localhost。`DATABASE_URL` 必須指向 Bot 共用的資料庫。

### Judge 與題目資料

後端透過 JudgeProvider 呼叫選定的評測服務；預設 `JUDGE_PROVIDER=disabled`，設定 URL 不會自動啟用。
開發環境可使用 Mock（不執行程式碼），production 禁用 Mock。
既有 Judge0 adapter 保留，需明確選擇 `JUDGE_PROVIDER=judge0`；瀏覽器不取得 Judge 憑證，也不直接呼叫 Judge。
選用的真正 Judge 部署必須強制 CPU、記憶體、執行逾時、檔案系統隔離與禁網。

資料集目前只有題號/名稱/難度及 UVa 外部連結，沒有題目敘述與測資。遷移後 `problems` 新增敘述、sample、discussion URL 及 `test_cases` 欄位；題目頁會保留 UVa 來源連結，敘述未匯入時顯示提醒。管理者須從具授權的來源填入資料。`test_cases` 是 JSON array，例如：

```json
[{"input":"2 3\n","output":"5\n","hidden":false},{"input":"10 20\n","output":"30\n","hidden":true}]
```

`Run` 僅執行 sample 或自訂輸入，不建正式 submission。`Submit` 建立 Pending 紀錄，由背景工作逐筆送到 Judge0，測資比對通過後更新 Accepted 並沿用共用解題表。只回傳標記 `hidden:false` 的失敗測資；隱藏測資細節保留在伺服器。現有系統沒有全站管理員角色，所以提交程式碼 API 只允許本人讀取。

### Website API

- `GET /auth/login?next=/problems/{id}`、`GET /auth/callback`、`POST /auth/logout`
- `POST /api/problems/{id}/run`：以 Sample/Custom Input 執行，不存正式提交。
- `POST /api/problems/{id}/submit`：建立提交並排入 Judge 工作。
- `GET /api/submissions/{id}`：本人查詢評測結果。
- `GET /api/submissions/{id}/code`：本人取得完整程式碼。
- Pages: `/`, `/problems`, `/problems/{id}`, `/submissions`, `/leaderboard`。

### Migration

執行 `alembic upgrade head` 套用 `0004_website_practice`、`0005_problem_memory_limit`、`0006_submission_failure_details`：沿用現有 users/profiles 加 Discord avatar、沿用 problems 加網站題目欄位，並擴充 submissions 以記錄網站程式碼、語言、結果與執行資訊。Bot 原有 submission 的 uHunt ID 仍保留；網站 submission 使用 nullable `external_submission_id`，不另建第二套資料庫。

### Development fixture 與驗證

`tests/fixtures/uva100_development.json` 是僅供測試的 UVa 100 題目 fixture，包含題目說明、sample、4 組本專案自建測資、3 秒時限及 128 MiB 記憶體限制。檔案標記 `official_judge_data: false`，**不是 UVa 官方 judge data**，不會由應用程式或 migration 自動載入正式資料庫。

執行 mock 核心測試與整套測試：

```bash
python -m pytest -q tests/test_website_judge.py
python -m pytest -q
```

需要設定可用 Judge0 base URL 及必要憑證，才可執行會真的連外評測的整合測試：

```bash
JUDGE0_URL=https://your-judge0.example/api
JUDGE0_API_KEY=your-secret
python -m pytest -m integration -q tests/test_website_judge.py
```

該 opt-in 測試透過網站 Submit、資料庫 Submission 與 solved 記錄，向 Judge0 實送 C/C++/Python Accepted，以及 Wrong Answer、Compilation Error、Runtime Error、Time Limit Exceeded 範例。未設定 `JUDGE0_URL` 時會 skip，不會把 mock 結果當成真實服務驗證。

執行真實 Judge 測試另外需要明確設定 `RUN_JUDGE0_INTEGRATION=1`；只有 endpoint 設定不會自動連外。

### 平台擴充 Phase 1

完整現況與後續缺項見 [Website audit](docs/WEBSITE_AUDIT.md)。沿用既有 FastAPI HTML 與 Discord OAuth，
登入首頁現在包含題庫解題進度、最近提交、最近未解題的續作入口及共同排行榜摘要。
`/ranking` 與既有 `/leaderboard` 共用同一頁面與 Bot RankingService；`/contest` 目前僅為入口提示。
Phase 1 的完整現況與後續變更分別記錄於 audit 與下列 Phase 2–4 文件。

Phase 1 不需額外 migration。開發驗證：`python -m pytest -q`。

### Phase 2–4：Mock Online Judge workspace

詳見 [交付、開發操作與驗證紀錄](docs/PHASE234.md)。包含題庫搜尋／完成篩選、Monaco split workspace、
四語言 metadata、草稿保存、RunService／WebsiteSubmissionService／JudgeProvider、queued/running/finished、
本人提交詳情、compiler message 清理與 Mock production 防護。
新增 migration `0007_submission_pipeline`。development fixture 必須以獨立資料庫與明確指令匯入，沒有 production seed。
已驗證 Mock browser flow；真實 Judge／OAuth／Ubuntu deployment 仍未驗證。
