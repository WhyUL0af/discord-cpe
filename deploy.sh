#!/usr/bin/env bash
# Publish a new immutable release, preserving external settings and database data.
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/deploy/ubuntu/common.sh"
require_host

DEPLOY_REF=${1:-main}
REPO_URL=https://github.com/WhyUL0af/discord-cpe.git
RELEASE_ID="$(date +%Y%m%d-%H%M%S)-$$"
NEW_RELEASE="$RELEASE_BASE/$RELEASE_ID"
OLD_RELEASE=""
CUTOVER_STARTED=0
if [[ -L "$CURRENT_LINK" ]]; then
    OLD_RELEASE=$(checked_release "$CURRENT_LINK")
elif [[ -e "$CURRENT_LINK" ]]; then
    fail "$CURRENT_LINK 必須是 symlink。"
fi

recover_on_error() {
    local code=$?
    trap - ERR
    log "部署失敗；新版本不會被標示為部署成功。" >&2
    if [[ $CUTOVER_STARTED == 1 && -n "$OLD_RELEASE" ]]; then
        log "嘗試重新啟動原版本：$OLD_RELEASE" >&2
        if compose_at "$OLD_RELEASE" up -d --build postgres discord-bot; then
            log "原版本啟動指令已執行；請檢查 Bot 日誌與 migration 狀態。" >&2
        else
            log "原版本恢復失敗，請人工處理。" >&2
        fi
    fi
    log "資料庫不會自動降版或還原；備份位於 $BACKUP_BASE。" >&2
    exit "$code"
}
trap recover_on_error ERR

log "建立版本 $RELEASE_ID（分支或 tag：$DEPLOY_REF）"
git clone --depth 1 --single-branch --branch "$DEPLOY_REF" "$REPO_URL" "$NEW_RELEASE"
compose_at "$NEW_RELEASE" config --quiet
compose_at "$NEW_RELEASE" build discord-bot

# Preserve the original code snapshot without following the external .env symlink.
if [[ -n "$OLD_RELEASE" ]]; then
    snapshot=$(mktemp "$BACKUP_BASE/.release-${RELEASE_ID}.XXXXXX")
    tar -czf "$snapshot" -C "$OLD_RELEASE" .
    mv "$snapshot" "$BACKUP_BASE/release-${RELEASE_ID}.tar.gz"
fi

compose_at "$NEW_RELEASE" up -d postgres
wait_postgres
backup_database "$RELEASE_ID"

# Stop the former optional website so notification mode runs only Postgres and Bot.
if [[ $(docker inspect --format '{{.State.Running}}' cpe-website 2>/dev/null || true) == true ]]; then
    compose_at "$NEW_RELEASE" --profile website stop website
fi
STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CUTOVER_STARTED=1
compose_at "$NEW_RELEASE" up -d --no-deps --force-recreate discord-bot
if ! wait_bot "$STARTED_AT"; then
    log "Bot 在 120 秒內沒有成功連線 Discord。" >&2
    false
fi
compose_at "$NEW_RELEASE" exec -T discord-bot alembic current

if [[ -n "$OLD_RELEASE" ]]; then
    set_link "$OLD_RELEASE" "$PREVIOUS_LINK"
fi
set_link "$NEW_RELEASE" "$CURRENT_LINK"
CUTOVER_STARTED=0
trap - ERR
log "部署成功：$NEW_RELEASE"
git -C "$NEW_RELEASE" log -1 --format='%h %s'
compose_at "$NEW_RELEASE" ps
log "舊版本與備份均保留；不自動刪除 release 或資料庫 volume。"
