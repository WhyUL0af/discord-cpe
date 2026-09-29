# Discord 通知與 CPE 風格模擬考

## 目前流程

Discord 題目通知 → 使用者自行至 UVa Online Judge 提交 → uHunt → PostgreSQL → 點「查看提交結果」取得頻道內私人回覆，排行榜自動更新。

不發送 Discord 私訊。頻道名稱、權限與可直接貼上的說明見 [Discord 頻道配置](DISCORD_CHANNELS.md)。

每天沿用 `/setup` 所設定的每日一題頻道。模擬考由有「管理訊息」權限的成員在模擬考文字頻道執行 `/mock_exam`，公開發送一次題組；不另設自動模擬考排程。

## 模擬考選題

- 從 `app/data/mock_exam_pool.json` 隨機組合，沒有儲存或抽取歷屆完整試卷。
- 7 題不重複，由易到難：2 基礎、2 中階、2 進階、1 挑戰。
- 至少 1 題一星選集題、至少 4 種題型、同一題型最多 2 題。
- 難度與題型是本站維護的練習評估，**不是官方 CPE 星等或官方固定出題比例**。
- 題型只供內部選題，不在通知中透露解題演算法。
- 發送前以 uHunt `/p/num/{number}` 確認 UVa 題號、標題及 PID；無法取得必要資料就不發送不完整題組。
- 3 小時為通知中的練習時間提示，不會禁止 UVa 提交或切斷追蹤。排行榜是累計及週榜，沒有另建單場比賽計分系統。
- 目前選題池 18 題，跨場可能重複；可以擴充此 JSON 增加變化。每日一題仍用既有 CPE 精選題庫及冷卻設定。

官方參考：[CPE 公告](https://cpe.cse.nsysu.edu.tw/newest.php)、[一星選集](https://cpe.cse.nsysu.edu.tw/environment.php)。題目資訊來自 [uHunt API](https://uhunt.onlinejudge.org/api)，題目連結為 UVa 官方 PDF。

## 追蹤與排行榜

1. 成員先 `/link <uva_username>`；此指令驗證公開 UVa 帳號存在，並非 UVa 帳號所有權認證。
2. Bot 輪詢所有已綁定成員，不要求建立單題 session，可同時解七題。
3. 只查詢資料庫中已知 PID 的題目：既有每日題庫、已發布模擬考題目及已加入的 UVa 題目。不是完整 UVa 生涯題數；`/profile` 才是 uHunt 公開生涯統計。
4. `/subs-pids` 每批最多 100 題；首次同步、Bot 重啟或題庫改變時，補入該題庫的歷史紀錄，不主動發通知。使用者點按鈕後可查詢已同步的紀錄。
5. 後續採提交 ID 增量查詢；尚在佇列或無法評判的紀錄會重新查詢，允許同一 submission 更新成 Accepted。
6. 提交 ID 唯一。先提交資料庫交易，再推進記憶體游標；uHunt 失敗時不推進游標。背景同步不發訊息或私訊。
7. 排行榜、已解清單及每日解題統計只認 `source=uhunt`、非空外部提交 ID 的 Accepted；網站與 Mock 成績不計入。
8. 累計榜按不同題目數排序；週榜按每人每題最早外部 Accepted 時間是否在本週計數（週一 00:00 UTC）；每日解題統計使用台北時區日期。重複 AC 增加提交數，不增加解題數。相同題數以 Discord User ID 穩定排列，不使用競賽罰時。
9. 現有排行榜是共用 Bot 資料庫範圍，沒有 Discord guild 成員過濾。多帳號綁同一 UVa 帳號不會重複分配同一外部提交，但不應如此設定。

## 頻道內私人結果查詢

- 每日一題、自主練習題目卡片及模擬考提供「🔄 查看提交結果」按鈕；刷題中心亦提供查詢入口。
- 每次依點擊者的 Discord User ID 找到綁定的 User，只讀該 User 的外部 uHunt 提交。
- 單題卡片查該題；模擬考通知查原題組；刷題中心查已知題庫最近 10 筆。
- 題目範圍從原通知 embed 的 UVa 題號恢復，不會在重啟後改成新題組；查詢按鈕使用 persistent view。
- 回覆使用 Discord Ephemeral，只有點擊者可見。按鈕不開始計時、不建立 Submission，也不觸發 UVa 提交。
- 查詢讀取已同步資料，不即時呼叫 uHunt。包含目前仍在 Queued 的狀態；使用者可稍候重新查詢。
- 不顯示程式碼、hidden test data 或其他使用者的提交。
- 更新部署後，刷題中心會自動更新；既有每日及模擬考訊息不自動補按鈕，新通知會使用新入口。舊題結果仍可在刷題中心查詢。

## Ubuntu 部署

正式部署採與 OSV 相同的 `releases/current` 方式，完整首次切換、更新與回滾指令見 [Ubuntu 部署手冊](../DEPLOY_UBUNTU.md)。不要在運行中的版本目錄直接 git pull。

預設只啟動 `postgres` 與 `discord-bot`，網站服務改成 `website` Compose profile。沿用目前 `/etc/discord-cpe/.env` 的位置，不把秘密貼入聊天或提交 Git。

必要設定：

```dotenv
DISCORD_TOKEN=<你的 Bot Token>
POSTGRES_PASSWORD=<資料庫強密碼>
DATABASE_URL=postgresql+asyncpg://postgres:<URL-encoded-password>@postgres:5432/cpe_bot
UHUNT_BASE_URL=https://uhunt.onlinejudge.org/api
UHUNT_TIMEOUT_SECONDS=10
SUBMISSION_POLL_INTERVAL=20
DAILY_REPEAT_COOLDOWN_DAYS=30
LOG_LEVEL=INFO
JUDGE_PROVIDER=disabled
```

Compose 會以 `POSTGRES_PASSWORD` 組合容器的 `DATABASE_URL`。依現有 Compose 寫法，密碼需避免 URL 保留字元，可採長隨機英數字密碼。OAuth、網站網域及 Judge0 設定不是此流程的必要條件。

```bash
docker compose --env-file /etc/discord-cpe/.env up -d --build postgres discord-bot
docker compose --env-file /etc/discord-cpe/.env logs -f discord-bot
```

若舊部署已啟動網站容器，profile 不會自動停止它；先執行：

```bash
docker compose --env-file /etc/discord-cpe/.env --profile website stop website
```

沒有新增資料模型或 migration。既有資料表、網站原始碼與測資保留，通知模式不使用網站評測。

## 上線人工檢查

- `/setup` 設每日頻道、刷題頻道及排行榜頻道。
- `/link` 後等待首次同步完成，確認 `/cpe solved` 與 `/rank all` 顯示題庫中的真實 Accepted。
- 有管理訊息權限的成員在模擬考頻道執行 `/mock_exam`，確認有 7 個不同題號、難度順序、3 小時提示及可開啟的 UVa 題目連結。
- 自行在 UVa 提交題庫中的題目，點「查看提交結果」確認私人回覆與資料庫結果，確認不會收到私訊。測試重複 AC 時解題數不變。
- 兩位使用者點同一則通知，確認各自只看到本人結果；未綁定帳號顯示綁定提示。
- 提交 WA、CE，確認只更新提交結果，不增加已解題數。
- 測試 Queued → Accepted，同一外部提交 ID 不產生第二筆 submission。
- 重啟 Bot，確認歷史回填不洗版；已入庫的重複結果不重複計分。
- 這份清單是待執行流程，不代表已完成真實 Discord/UVa 上線驗證。本次未執行 pytest，前一階段測試數不能當作本次改動的測試結果。
