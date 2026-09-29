# discord-cpe：Ubuntu release 部署

採用與 OSV 相同的目錄分工：每次建立新的版本目錄，應用程式以 Docker Compose 執行，機密與資料庫資料放在版本之外。

```text
/opt/discord-cpe/releases/<release-id>    每次 clone 的版本
/opt/discord-cpe/current                 成功部署的版本 symlink
/opt/discord-cpe/previous                上一個版本 symlink
/etc/discord-cpe/.env                    既有秘密設定
/srv/discord-cpe/backups                 程式快照與 PostgreSQL SQL 備份
Docker volume: cpe_postgres_data         沿用既有資料庫
```

舊 `/opt/discord-cpe/release/`、`backup/`、`backups/` 都保留，不搬動或刪除。`current` 原本指向舊 `release/` 時也可以部署及回滾。之後建立的版本放在 `releases/`，新備份放在 `/srv/discord-cpe/backups`。

## 1. Windows：先提交並推送

在本機 PowerShell 執行。任何步驟失敗先停止，不要繼續下一步。

```powershell
cd C:\me\Projects\discord-cpe
git status --short
git diff --check
git add .
git diff --cached --stat
git commit -m "Align discord-cpe Ubuntu deployment with OSV release workflow"
git push origin main
```

確認 staged 檔案符合預期。`.env` 被忽略，不要強制加入秘密。

## 2. Ubuntu：準備目錄與既有設定

```bash
sudo install -d -m 0755 /opt/discord-cpe/releases
sudo install -d -m 0700 /srv/discord-cpe/backups
sudo install -d -m 0750 /etc/discord-cpe
```

已有 `/etc/discord-cpe/.env` 就沿用，**不覆蓋為範本**。必要時編輯：

```bash
sudo nano /etc/discord-cpe/.env
sudo chmod 600 /etc/discord-cpe/.env
```

至少設定 `DISCORD_TOKEN`、`POSTGRES_PASSWORD`。既有 PostgreSQL volume 的密碼必須保持一致；改 `.env` 不會重設資料庫內的密碼。其他選項見 `.env.example`。通知模式不需要 OAuth、網站網域或 Judge0。

## 3. 第一次切換：取得新版部署腳本

你目前 `current` 仍是舊版本，不能直接執行裡面的舊 `deploy.sh`。先取得已推送的新版本作為部署工具入口；不修改舊版本：

```bash
bootstrap_release="/opt/discord-cpe/releases/bootstrap-$(date +%Y%m%d-%H%M%S)"
sudo git clone --depth 1 --single-branch --branch main \
  https://github.com/WhyUL0af/discord-cpe.git "$bootstrap_release"
```

若曾安裝原生 Python 的 `cpe-bot.service`，或服務目前仍在運行，先停止它，避免兩個 Bot 程序同時運作：

```bash
if sudo systemctl is-active --quiet cpe-bot.service; then
  sudo systemctl stop cpe-bot.service
fi
```

以新版腳本部署：

```bash
sudo bash "$bootstrap_release/deploy.sh" main
```

`main` 必須已包含本次修改。可把參數改成現有 branch 或 tag；腳本不接受裸 commit SHA。

## 4. 部署腳本做什麼

1. 檢查 Docker Compose、外部 `.env` 及部署鎖，避免同時部署或回滾。
2. Clone branch/tag 到新的 `releases/<時間>-<PID>`。
3. 用 `compose config --quiet` 驗證設定，不印出展開後的秘密。
4. 建置 Bot image；程式碼包含在 image 中，正式 Compose 不掛載工作目錄。
5. 備份舊版本程式碼（不追隨 `.env` symlink）。
6. 啟動並確認 PostgreSQL 健康，執行 `pg_dump`；失敗就停止，不忽略備份錯誤。
7. 停止舊可選網站，啟動新版 Bot。容器入口自動執行 `alembic upgrade head`。
8. 最多等待 120 秒，確認 Bot 的 Discord ready 日誌及容器仍在運行。
9. 顯示 `alembic current`，更新 `previous` 與 `current`，列出容器狀態。

切換後的啟動檢查失敗會嘗試重新啟動原版本，但不宣稱已成功復原，仍需檢查日誌。資料庫不自動降版或還原，已執行的 migration 可能需要另外處理。

這是單一 Bot 重啟部署，**不是零停機部署**。舊版本與 SQL 備份均保留，不執行自動刪除或 `docker compose down -v`。

## 5. 安裝 systemd：開機啟動 Compose

新版 `cpe-bot.service` 與 OSV 一樣使用 `Type=oneshot`、`RemainAfterExit=yes`，管理 Compose；不再直接啟動 host Python。

```bash
sudo install -m 0644 /opt/discord-cpe/current/cpe-bot.service \
  /etc/systemd/system/cpe-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now cpe-bot.service
sudo systemctl status cpe-bot.service --no-pager
```

`active (exited)` 是此類 Compose 管理單元的正常狀態，仍須用容器狀態及 Bot 日誌確認實際運作。容器的 `restart: unless-stopped` 負責自動重啟。

## 6. 後續更新

Windows 提交並推送後，在 Ubuntu 執行：

```bash
sudo bash /opt/discord-cpe/current/deploy.sh main
```

每次建立新版本；不在 current 裡 `git pull`，也不直接覆寫既有版本。

## 7. 查看狀態與日誌

可以從任何工作目錄執行，明確指定 Compose 設定檔：

```bash
sudo docker compose --project-name cpe-bot \
  --env-file /etc/discord-cpe/.env \
  -f /opt/discord-cpe/current/docker-compose.yml ps

sudo docker compose --project-name cpe-bot \
  --env-file /etc/discord-cpe/.env \
  -f /opt/discord-cpe/current/docker-compose.yml logs --tail=100 discord-bot

sudo docker compose --project-name cpe-bot \
  --env-file /etc/discord-cpe/.env \
  -f /opt/discord-cpe/current/docker-compose.yml exec -T discord-bot alembic current
```

不要把 `.env` 或完整 `docker compose config` 輸出貼到聊天。

## 8. 回滾應用程式

回到 previous：

```bash
sudo bash /opt/discord-cpe/current/rollback.sh
```

或指定既有版本目錄名稱（支援新 `releases/` 與舊 `release/`）：

```bash
sudo bash /opt/discord-cpe/current/rollback.sh 20260924_222658
```

回滾前同樣備份當前資料庫；重建並確認目標 Bot 連線成功後，才更新 current。這只回滾程式碼，**不還原資料庫 schema 或資料**。舊程式與新 migration 是否相容需確認；備份位於 `/srv/discord-cpe/backups`。

## 9. Discord 人工驗證

- `/practice_center` 固定面板及題目入口正確。
- `/link` 成功或失敗只有本人可見。
- 兩位使用者點同一個「查看提交結果」，各自只看到本人紀錄。
- 自行到 UVa 提交後，背景同步結果；不發評測私訊。
- 重複 AC 不增加已解題數。
- `/mock_exam` 發送 7 題與結果查詢入口。

目前僅完成腳本及設定的本機靜態檢查。實際 Ubuntu Docker 建置、備份、migration、Discord ready、systemd 與回滾仍需在主機上執行確認。
