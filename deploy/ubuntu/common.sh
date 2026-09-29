#!/usr/bin/env bash
# Shared deployment paths and checks. Do not print resolved environment values.
set -Eeuo pipefail

APP_ROOT=/opt/discord-cpe
RELEASE_BASE="$APP_ROOT/releases"
BACKUP_BASE=/srv/discord-cpe/backups
CURRENT_LINK="$APP_ROOT/current"
PREVIOUS_LINK="$APP_ROOT/previous"
ENV_PATH=/etc/discord-cpe/.env

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

require_host() {
    [[ $EUID -eq 0 ]] || fail "請用 sudo bash 執行部署腳本。"
    command -v docker >/dev/null || fail "找不到 Docker。"
    command -v git >/dev/null || fail "找不到 Git。"
    command -v flock >/dev/null || fail "找不到 flock。"
    docker compose version >/dev/null
    [[ -f "$ENV_PATH" ]] || fail "請先設定 $ENV_PATH，不要把秘密貼到聊天。"
    chmod 600 "$ENV_PATH"
    grep -Eq '^DISCORD_TOKEN=.+$' "$ENV_PATH" || fail "請設定 DISCORD_TOKEN。"
    if grep -q 'your_discord_bot_token_here' "$ENV_PATH"; then
        fail "請在 $ENV_PATH 設定真正的 DISCORD_TOKEN。"
    fi
    install -d -m 0755 "$APP_ROOT" "$RELEASE_BASE"
    install -d -m 0700 "$BACKUP_BASE"
    exec 9>"$APP_ROOT/.deployment.lock"
    flock -n 9 || fail "另一次部署或回滾正在執行。"
}

compose_at() {
    local directory=$1
    shift
    docker compose --project-name cpe-bot --project-directory "$directory" \
        --env-file "$ENV_PATH" -f "$directory/docker-compose.yml" "$@"
}

checked_release() {
    local directory
    directory=$(readlink -e "$1") || fail "版本目錄不存在：$1"
    case "$directory" in
        "$APP_ROOT"/releases/*|"$APP_ROOT"/release/*) ;;
        *) fail "版本路徑必須位於 $APP_ROOT/releases 或舊 release 目錄。" ;;
    esac
    [[ -f "$directory/docker-compose.yml" ]] || fail "版本中找不到 docker-compose.yml。"
    printf '%s\n' "$directory"
}

set_link() {
    local target=$1 link=$2 temporary
    [[ ! -e "$link" || -L "$link" ]] || fail "$link 不是 symlink，請先人工確認。"
    temporary="${link}.pending.$$"
    ln -s "$target" "$temporary"
    mv -Tf "$temporary" "$link"
}

wait_postgres() {
    local attempt
    for attempt in $(seq 1 30); do
        if [[ $(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' cpe-postgres 2>/dev/null || true) == healthy ]]; then
            return 0
        fi
        sleep 2
    done
    fail "PostgreSQL 未通過健康檢查。"
}

wait_bot() {
    local since=$1 attempt output
    for attempt in $(seq 1 60); do
        output=$(docker logs --since "$since" cpe-discord-bot 2>&1 || true)
        if grep -Fq 'CPE Discord Bot is online and ready.' <<<"$output"; then
            [[ $(docker inspect --format '{{.State.Running}}' cpe-discord-bot 2>/dev/null || true) == true ]] && return 0
        fi
        sleep 2
    done
    return 1
}

backup_database() {
    local label=$1 temporary
    temporary=$(mktemp "$BACKUP_BASE/.database-${label}.XXXXXX")
    docker exec cpe-postgres pg_dump -U postgres cpe_bot >"$temporary"
    [[ -s "$temporary" ]] || fail "資料庫備份是空檔，停止部署。"
    mv "$temporary" "$BACKUP_BASE/database-${label}.sql"
    log "資料庫備份：$BACKUP_BASE/database-${label}.sql"
}
