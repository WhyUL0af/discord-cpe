# CPE Discord Bot

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.3+-blueviolet.svg)](https://github.com/Rapptz/discord.py)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)

專為台灣大專院校與程式競賽社群打造的 **CPE (Collegiate Programming Examination) Discord 刷題機器人**。讓伺服器成員可以直接在 Discord 內綁定 UVa Online Judge 帳號、取得 CPE 常考與一星題目、開啟個人專屬 Thread 刷題空間，並自動追蹤 UVa 上的評測提交結果（AC、WA、TLE、CE 等）以即時更新進度與伺服器排行榜。

> [!IMPORTANT]
> **非評判系統聲明 (No Custom Judge Policy)**：
> 本機器人**不是 Online Judge**，不包含任何本機編譯、沙盒環境（Docker Sandbox）或執行使用者程式碼的行為。所有題目的程式碼評測皆由 **UVa Online Judge** 官方伺服器執行，Bot 僅透過官方授權的 uHunt API 進行提交追蹤與數據統計。

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
> 若部署於 Ubuntu 伺服器，專案已附帶自動化安裝腳本 `deploy.sh` 與專門的 [Ubuntu 部署手冊 (DEPLOY_UBUNTU.md)](file:///c:/me/Projects/discord-cpe/DEPLOY_UBUNTU.md)。

1. 確保已建立 `.env` 並填入 `DISCORD_TOKEN`。
2. 執行啟動指令：
   ```bash
   docker compose up -d --build
   ```
3. 查看即時日誌：
   ```bash
   docker compose logs -f discord-bot
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
├── 🎯・每日一題
├── 💻・刷題區
├── 🏆・排行榜
└── 💬・題目討論
```

加入伺服器後，具有**管理員權限**的成員執行 `/setup` 綁定頻道：

```
/setup daily_channel:#🎯・每日一題 practice_channel:#💻・刷題區 ranking_channel:#🏆・排行榜 discussion_channel:#💬・題目討論 archive_on_solve:false
```

- **每日一題頻道**：每天固定時間發布一則挑戰題，並提供快捷作答按鈕。
- **刷題區**：使用者調用 `/problem` 或點擊按鈕時自動建立個人作答 Thread 的主要入口。
- **排行榜頻道**：Bot 會發送一則常駐排行榜訊息，日後透過 `message.edit()` 自動更新，不洗頻。

---

## 9. Slash Commands 指令全覽

| 指令 | 說明 | 範例 |
|---|---|---|
| `/setup` | 設定伺服器各專用頻道（僅管理員可用） | `/setup daily_channel:#每日一題` |
| `/link <uva_username>` | 驗證並綁定個人 UVa 帳號 | `/link WhyUL0af` |
| `/unlink` | 解除目前 Discord 帳號所綁定的 UVa 帳號 | `/unlink` |
| `/profile [member]` | 查看個人或指定成員的 UVa 解題與提交統計數據 | `/profile` 或 `/profile member:@Alex` |
| `/problem random` | 隨機取得一題 CPE 題目 | `/problem random` |
| `/problem number <num>` | 根據題號精準取得題目 | `/problem number 100` |
| `/problem easy` | 隨機取得一題 CPE 一星常考題（⭐） | `/problem easy` |
| `/status` | 查看目前進行中的題目與作答 Thread | `/status` |
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

系統採用**按需輪詢 (On-Demand Polling)** 策略，嚴格遵守 Rate Limit，不浪費伺服器資源：

1. **僅追蹤活躍使用者 (Active Sessions Only)**：
   只有使用者在刷題區或每日一題點擊「💻 開始作答」並建立 Thread 後，才會進入追蹤佇列。平時不掃描伺服器所有成員的提交。
2. **防重複通知與重啟復原 (Idempotency & Last Submission ID)**：
   當開啟 Session 時，系統會記錄使用者在 UVa 上的 `last_submission_id`。重啟 Bot 後，不會將過去已 AC 的歷史提交當作新事件重複發布。
3. **Verdict 狀態映射**：
   - 提交進入佇列：`⏳ In Queue / Judging...`
   - 通過評測：`✅ Accepted`（在 Thread 標記完成、將 Thread 標題改為 `✅ UVa 100｜User`，並記錄於 `user_solved_problems` 表）
   - 未通過評測：正確顯示 `❌ Wrong Answer`、`⏱ Time Limit Exceeded`、`🛠 Compilation Error`、`💥 Runtime Error` 等對應狀態與嘗試次數 (Attempts)。
4. **Thread 防重複建立**：
   若同一位使用者對同一道題目已有進行中的 Thread，再次點擊「開始作答」會直接指引至原 Thread，避免洗版。

---

## 12. 每日一題與選題機制 (Daily Problem)

- 每日一題由背景排程自動選出，排程器會排除最近 `DAILY_REPEAT_COOLDOWN_DAYS`（預設 30 天）內出現過的題目。
- 每日一題會寫入資料庫 `daily_problems` 表，因此 **Bot 重啟後絕對不會重新抽題**。
- 題目卡片包含：
  - `[📖 查看題目]`：直連官方題目 PDF / 說明頁。
  - `[💻 開始作答]`：直接開啟專屬 Thread。
  - `[📊 查看統計]`：即時查詢今日有哪些成員已 AC 本題。

---

## 13. 排行榜統計與常駐訊息 (Leaderboard)

- **去重計分規則**：排名嚴格以 **Solved Problems (不重複解出題目數)** 為主，同一題即使提交 AC 10 次，也僅計為 1 題。
- **即時更新機制**：Bot 定時透過 `message.edit()` 刷新常駐排行榜訊息，包含：
  - 前十名榜單（附金、銀、銅牌勳章與 UVa 帳號）
  - 本週伺服器總 Submissions 與 Accepted 統計
- 支援 `/rank weekly`（本週解題榜）與 `/rank all`（歷史總榜）。

---

## 14. 常見問題與疑難排解 (Troubleshooting)

### Q1: 點擊「開始作答」提示「尚未綁定 UVa Account」？
請先在任意頻道執行 `/link <你的UVa帳號>`，驗證成功後方可開始建立刷題空間。

### Q2: 在 UVa 提交程式碼後，Discord Thread 沒有更新？
1. 請確認提交時選擇的題目題號與 Thread 題號一致。
2. UVa / uHunt 本身可能偶有數秒至數十秒的評判延遲，預設輪詢間隔為 20 秒，請稍候。
3. 檢查 Bot 日誌是否出現 `uHunt API timeout` 或連線異常。

### Q3: 機器人重啟後，正在進行的 Thread 是否還會繼續追蹤？
會的。所有進行中的 Session 均持久化儲存於 PostgreSQL，Bot 重啟後會自動讀取所有 `status = 'active'` 的 Session 繼續追蹤。

### Q4: 如何執行單元測試？
本專案包含 18+ 個單元與整合測試，包含記憶體資料庫 (aiosqlite) 與模擬外部 API 測試：
```bash
pytest -v
```
