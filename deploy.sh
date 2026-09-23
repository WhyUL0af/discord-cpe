#!/usr/bin/env bash
# ==============================================================================
# CPE Discord Bot - Enterprise Zero-Downtime Deployment Script
# Architecture:
#   /opt/discord-cpe/
#   ├── current -> release/<timestamp>  (Symlink to active release)
#   ├── release/                        (Historical versioned releases)
#   └── backup/                         (Snapshot backups before new deployments)
# Configuration:
#   /etc/discord-cpe/.env
# ==============================================================================

set -euo pipefail

APP_ROOT="/opt/discord-cpe"
RELEASE_BASE="$APP_ROOT/release"
BACKUP_BASE="$APP_ROOT/backup"
CURRENT_LINK="$APP_ROOT/current"
ENV_PATH="/etc/discord-cpe/.env"
REPO_URL="https://github.com/WhyUL0af/discord-cpe.git"
KEEP_RELEASES=5

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN}   CPE Discord Bot - Deployment (release/current/backup)${NC}"
echo -e "${GREEN}======================================================${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed! Please install Docker first."
    exit 1
fi

# 1. Ensure directory structure exists
mkdir -p "$RELEASE_BASE" "$BACKUP_BASE" "/etc/discord-cpe"

# 2. Check /etc/discord-cpe/.env
if [ ! -f "$ENV_PATH" ]; then
    log_error "$ENV_PATH does not exist! Please create it first."
    echo "Run: sudo nano $ENV_PATH"
    exit 1
fi

chmod 600 "$ENV_PATH"

if grep -q "your_discord_bot_token_here" "$ENV_PATH" || ! grep -q "^DISCORD_TOKEN=" "$ENV_PATH"; then
    log_error "DISCORD_TOKEN in $ENV_PATH is still unset or placeholder!"
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
NEW_RELEASE_DIR="$RELEASE_BASE/$TIMESTAMP"

# 3. Backup current active release if it exists
if [ -L "$CURRENT_LINK" ] && [ -d "$CURRENT_LINK" ]; then
    PREV_TARGET=$(readlink -f "$CURRENT_LINK")
    BACKUP_FILE="$BACKUP_BASE/backup_${TIMESTAMP}.tar.gz"
    log_info "Creating snapshot backup of active release to $BACKUP_FILE..."
    tar -czf "$BACKUP_FILE" -C "$RELEASE_BASE" "$(basename "$PREV_TARGET")" || log_warn "Backup tarball created with warnings."
    
    # Optional: Backup database if postgres container is running
    if docker ps --format '{{.Names}}' | grep -q "cpe-postgres"; then
        log_info "Backing up PostgreSQL database..."
        docker exec -t cpe-postgres pg_dump -U postgres cpe_bot > "$BACKUP_BASE/db_${TIMESTAMP}.sql" 2>/dev/null || true
    fi
fi

# 4. Clone new release from repository
log_info "Deploying new release to $NEW_RELEASE_DIR..."
git clone --depth 1 "$REPO_URL" "$NEW_RELEASE_DIR"

# Ensure local .env in new release points to /etc/discord-cpe/.env
ln -sf "$ENV_PATH" "$NEW_RELEASE_DIR/.env"

# 5. Atomically switch 'current' symlink to new release
log_info "Switching 'current' symlink to $NEW_RELEASE_DIR..."
ln -sfn "$NEW_RELEASE_DIR" "$CURRENT_LINK"

# 6. Build and launch containers from current
log_info "Building and launching containers via Docker Compose..."
cd "$CURRENT_LINK"
docker compose up -d --build

# 7. Cleanup old releases (keep latest N)
log_info "Cleaning up old releases (keeping newest $KEEP_RELEASES)..."
cd "$RELEASE_BASE"
ls -dt */ 2>/dev/null | tail -n +$((KEEP_RELEASES + 1)) | xargs -I {} rm -rf "{}" || true

log_success "Deployment completed successfully!"
echo ""
echo -e "${GREEN}Current Active Release:${NC} $(readlink -f "$CURRENT_LINK")"
echo ""
docker compose ps
