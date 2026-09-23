# CPE Discord Bot - Ubuntu 部署手冊

本指南適用於 **Ubuntu 20.04 / 22.04 / 24.04 LTS** 伺服器（AWS EC2、GCP Compute Engine、DigitalOcean Droplet、Linode、自架主機等）。

---

## 方案 A：使用 Docker Compose 部署（強烈推薦）

Docker Compose 可以自動處理 Python 環境、PostgreSQL 資料庫、容器依賴健康檢查與開機自動重啟，是最乾淨且不容易出錯的方式。

### Step 1. 將程式碼上傳至 Ubuntu 主機

在您的本地電腦透過 Git 或 SCP 將專案傳至伺服器（建議放置於 `/opt/discord-cpe` 或使用者家目錄）：

```bash
# 方法 1：透過 Git Clone（推薦）
git clone <你的_REPOSITORY_URL> /opt/discord-cpe
cd /opt/discord-cpe

# 或方法 2：透過 SCP 上傳本地資料夾
scp -r c:\me\Projects\discord-cpe user@your-server-ip:/opt/discord-cpe
```

### Step 2. 設定環境變數 `.env`

```bash
cd /opt/discord-cpe
cp .env.example .env

# 設定安全權限，避免敏感 Token 洩漏
chmod 600 .env

# 編輯設定檔填入你的 DISCORD_TOKEN
nano .env
```

在 `.env` 中確認以下項目：
```ini
DISCORD_TOKEN=你的_DISCORD_BOT_TOKEN
# DATABASE_URL 在 docker-compose 內部會自動指定，維持預設即可
SUBMISSION_POLL_INTERVAL=20
DAILY_REPEAT_COOLDOWN_DAYS=30
AUTO_ARCHIVE_THREAD=false
LOG_LEVEL=INFO
```

### Step 3. 執行一鍵部署腳本（或手動執行 Compose）

我們提供了自動安裝 Docker 並啟動容器的腳本：

```bash
chmod +x deploy.sh
./deploy.sh
```

*(若偏好手動操作，可執行：)*
```bash
# 安裝 docker 與 docker-compose-plugin（若尚未安裝）
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

# 啟動服務（背景運行並自動建置映像）
docker compose up -d --build
```

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
cp .env.example .env
nano .env
```
修改 `.env` 中的 `DATABASE_URL`：
```ini
DATABASE_URL=postgresql+asyncpg://cpe_user:your_strong_password@localhost:5432/cpe_bot
DISCORD_TOKEN=你的_DISCORD_BOT_TOKEN
```

執行 Alembic 資料庫 Migration：
```bash
alembic upgrade head
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
