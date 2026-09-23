#!/usr/bin/env bash
# ==============================================================================
# CPE Discord Bot - Rollback Script
# Roll back 'current' symlink to the previous release
# ==============================================================================

set -euo pipefail

APP_ROOT="/opt/discord-cpe"
RELEASE_BASE="$APP_ROOT/release"
CURRENT_LINK="$APP_ROOT/current"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

cd "$RELEASE_BASE"
RELEASES=($(ls -dt */ 2>/dev/null | tr -d '/'))

if [ "${#RELEASES[@]}" -lt 2 ]; then
    log_error "No previous release found in $RELEASE_BASE to roll back to!"
    exit 1
fi

CURRENT_TARGET=$(basename "$(readlink -f "$CURRENT_LINK")")
PREVIOUS_RELEASE="${RELEASES[1]}"

log_info "Active release:   $CURRENT_TARGET"
log_info "Rolling back to:  $PREVIOUS_RELEASE"

ln -sfn "$RELEASE_BASE/$PREVIOUS_RELEASE" "$CURRENT_LINK"

cd "$CURRENT_LINK"
docker compose up -d --build

log_success "Successfully rolled back to $PREVIOUS_RELEASE!"
docker compose ps
