# CPE Discord Bot - Project Rules & Deployment Memory

## 伺服器部署規格 (Server Deployment Architecture)

- **主機目錄結構**：
  - 目錄根路徑：`/opt/discord-cpe`
  - 歷史發布版本目錄：`/opt/discord-cpe/release/<TIMESTAMP>`
  - 運行中軟連結 (Symlink)：`/opt/discord-cpe/current -> /opt/discord-cpe/release/<TIMESTAMP>`
  - 備份目錄：`/opt/discord-cpe/backup/`
  - 設定檔位置：`/etc/discord-cpe/.env`

---

## 初始部署流程 (First-Time Release)

伺服器初次建立並啟動服務時的標準步驟：

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

---

## 後續維護與更新流程

- **自動化發布新版本**：
  在 `/opt/discord-cpe/current` 下執行：
  ```bash
  chmod +x deploy.sh rollback.sh  # 若權限不足可先補上執行權限
  ./deploy.sh
  ```
  （會自動備份舊版本、拉取新代碼至新 release 目錄、切換 `current` 軟連結並重新建置容器）

- **版本回滾 (Rollback)**：
  若新發布版本有問題，於 `/opt/discord-cpe/current` 下執行：
  ```bash
  ./rollback.sh
  ```
