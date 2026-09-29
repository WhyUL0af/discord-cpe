#!/usr/bin/env bash
# Roll back application code only; database migrations are not reversed.
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/deploy/ubuntu/common.sh"
require_host
OLD_RELEASE=$(checked_release "$CURRENT_LINK")
if [[ -n ${1:-} ]]; then
    [[ $1 =~ ^[A-Za-z0-9_-]+$ ]] || fail "請提供版本目錄名稱，不要提供路徑。"
    if [[ -d "$RELEASE_BASE/$1" ]]; then
        TARGET=$(checked_release "$RELEASE_BASE/$1")
    else
        TARGET=$(checked_release "$APP_ROOT/release/$1")
    fi
else
    [[ -L "$PREVIOUS_LINK" ]] || fail "尚無 previous 版本；請提供要回滾的版本目錄名稱。"
    TARGET=$(checked_release "$PREVIOUS_LINK")
fi
[[ "$TARGET" != "$OLD_RELEASE" ]] || fail "指定版本已經是 current。"
compose_at "$TARGET" config --quiet
compose_at "$TARGET" build discord-bot
compose_at "$TARGET" up -d postgres
wait_postgres
backup_database "before-rollback-$(date +%Y%m%d-%H%M%S)-$$"
STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
compose_at "$TARGET" up -d --no-deps --force-recreate discord-bot
if ! wait_bot "$STARTED_AT"; then
    log "回滾版本未確認連線成功；current 保持原設定。" >&2
    compose_at "$OLD_RELEASE" up -d --build postgres discord-bot || true
    fail "請檢查 Bot 日誌。資料庫沒有自動降版或還原。"
fi
set_link "$OLD_RELEASE" "$PREVIOUS_LINK"
set_link "$TARGET" "$CURRENT_LINK"
log "應用程式回滾成功：$TARGET；資料庫 migration 維持原狀。"
compose_at "$TARGET" ps
