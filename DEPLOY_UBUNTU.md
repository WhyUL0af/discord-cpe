# CPE Discord Bot - Ubuntu 部署手冊

本指南適用於 **Ubuntu 20.04 / 22.04 / 24.04 LTS** 伺服器（AWS EC2、GCP Compute Engine、DigitalOcean Droplet、Linode、自架主機等）。

---

## 方案 A：使用 Docker Compose 部署（推薦，採 backup / release / current 架構）

採用業界標準的 Zero-Downtime 發布目錄結構：

```
/opt/discord-cpe/
├── current -> release/20260923_214500  # 指向當前正式運行的發布版本軟連結
├── release/                            # 儲存歷史各時間戳記版本
└── backup/                             # 部署前自動封存的快照與 DB Dump
/etc/discord-cpe/
└── .env                                # 外部共用敏感設定檔
```

### Step 1. 建立伺服器目錄結構與配置 `/etc/discord-cpe/.env`

```bash
# 1. 建立目錄結構並指派使用者權限
sudo mkdir -p /opt/discord-cpe/{release,backup}
sudo mkdir -p /etc/discord-cpe
sudo chown -R $USER:$USER /opt/discord-cpe

# 2. 建立設定檔
sudo nano /etc/discord-cpe/.env
```

在 `/etc/discord-cpe/.env` 中填入你的設定：
```ini
DISCORD_TOKEN=你的真實DiscordBotToken
SUBMISSION_POLL_INTERVAL=20
DAILY_REPEAT_COOLDOWN_DAYS=30
AUTO_ARCHIVE_THREAD=false
LOG_LEVEL=INFO
```
設定保護權限：
```bash
sudo chmod 600 /etc/discord-cpe/.env
```

### Step 2. 第一次部署（建立首個 release 與 current）

```bash
# 1. 產生第一版發布目錄
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
git clone https://github.com/WhyUL0af/discord-cpe.git /opt/discord-cpe/release/$TIMESTAMP

# 2. 建立 current 軟連結指向該版本
ln -sfn /opt/discord-cpe/release/$TIMESTAMP /opt/discord-cpe/current

# 3. 進入 current 啟動容器
cd /opt/discord-cpe/current
sudo docker compose up -d --build
```

### Step 3. 後續自動化部署與回滾

在 `/opt/discord-cpe/current` 內已附帶自動化腳本：
- **發布新版本**：直接執行 `./deploy.sh`，會自動：
  1. 備份上一版至 `/opt/discord-cpe/backup/`
  2. 拉取最新代碼至 `/opt/discord-cpe/release/<新時間戳記>`
  3. 平滑切換 `current` 軟連結並重新啟動容器
  4. 清理並保留最新 5 個歷史版本
- **快速回滾（Rollback）**：若新版本有問題，執行 `./rollback.sh` 即可瞬間將 `current` 切回上一版！



### Step 4. 檢查運行狀態與即時日誌

```bash
# 查看容器運行狀態 (狀態應為 Up / healthy)
docker compose ps

# 查看 Bot 即時運作日誌
docker compose logs -f discord-bot

# 查看資料庫日誌
docker compose logs -f postgres
```

### Step 5. 日常維護常用指令

```bash
# 重啟 Bot
docker compose restart discord-bot

# 停止所有服務
docker compose down

# 更新程式碼後重新建置啟動
git pull
docker compose up -d --build
```

---

## 方案 B：使用 Systemd 系統服務原生部署（無 Docker）

若您的 Ubuntu 伺服器已安裝共用的 PostgreSQL，或不希望使用 Docker，可使用 Systemd 管理守護進程。

### Step 1. 安裝系統依賴與 PostgreSQL

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib git
```

### Step 2. 建立專用資料庫與使用者

```bash
sudo -u postgres psql
```
在 psql 中執行：
```sql
CREATE DATABASE cpe_bot;
CREATE USER cpe_user WITH ENCRYPTED PASSWORD 'your_strong_password';
GRANT ALL PRIVILEGES ON DATABASE cpe_bot TO cpe_user;
ALTER DATABASE cpe_bot OWNER TO cpe_user;
\q
```

### Step 3. 建立 Python 虛擬環境與安裝依賴

```bash
sudo mkdir -p /opt/discord-cpe
sudo chown -R $USER:$USER /opt/discord-cpe
cd /opt/discord-cpe

# 放置程式碼於此目錄後：
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4. 設定環境變數與執行資料庫遷移

```bash
sudo mkdir -p /etc/discord-cpe
sudo cp /opt/discord-cpe/.env.example /etc/discord-cpe/.env
sudo chmod 600 /etc/discord-cpe/.env
sudo nano /etc/discord-cpe/.env
```
修改 `/etc/discord-cpe/.env` 中的 `DATABASE_URL` 與 `DISCORD_TOKEN`：
```ini
DATABASE_URL=postgresql+asyncpg://cpe_user:your_strong_password@localhost:5432/cpe_bot
DISCORD_TOKEN=你的_DISCORD_BOT_TOKEN
```

執行 Alembic 資料庫 Migration：
```bash
cd /opt/discord-cpe
ENV_FILE=/etc/discord-cpe/.env alembic upgrade head
```

### Step 5. 註冊 Systemd 系統服務（自動重啟與開機啟動）

將專案目錄下的 `cpe-bot.service` 複製至 systemd 目錄：
```bash
# 確認 cpe-bot.service 中的 User 與路徑與伺服器環境一致
sudo cp cpe-bot.service /etc/systemd/system/cpe-bot.service

# 重新載入 systemd 配置
sudo systemctl daemon-reload

# 啟用開機自啟動並立即啟動服務
sudo systemctl enable --now cpe-bot

# 查看服務運行狀態
sudo systemctl status cpe-bot

# 查看即時日誌
sudo journalctl -u cpe-bot -f
```

---

## 伺服器安全性最佳實踐 (Security Checklist)

1. **UFW 防火牆保護**：
   - 確保 PostgreSQL 的 5432 埠**不要**開放給公網。
   - 只允許 SSH (22) 與必要的網路流量：
     ```bash
     sudo ufw default deny incoming
     sudo ufw default allow outgoing
     sudo ufw allow 22/tcp
     sudo ufw enable
     ```
2. **保護 `.env` 權限**：
   - 確保除了執行 Bot 的使用者之外，其他帳號無法讀取：
     ```bash
     chmod 600 /opt/discord-cpe/.env
     ```
3. **資料庫定期備份**：
   可加入每日 crontab 自動備份資料：
   ```bash
   # Docker Compose 備份指令：
   docker compose exec -T postgres pg_dump -U postgres cpe_bot > /opt/backups/cpe_bot_$(date +%Y%m%d).sql
   ```
