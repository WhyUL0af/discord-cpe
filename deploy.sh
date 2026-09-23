#!/usr/bin/env bash
# ==============================================================================
# CPE Discord Bot - Ubuntu One-Click Deployment Script
# Supports: Ubuntu 20.04, 22.04, 24.04 LTS
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN}    CPE Discord Bot - Ubuntu Deploy Tool       ${NC}"
echo -e "${GREEN}===============================================${NC}"

# 1. Check Root / Sudo
if [ "$EUID" -ne 0 ]; then
    log_warn "This script is not running as root. You may be prompted for sudo password."
    SUDO="sudo"
else
    SUDO=""
fi

# 2. Check Docker installation
if ! command -v docker &> /dev/null; then
    log_info "Docker is not installed. Installing Docker..."
    $SUDO apt-get update -y
    $SUDO apt-get install -y ca-certificates curl gnupg lsb-release

    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null

    $SUDO apt-get update -y
    $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable --now docker
    log_success "Docker installed and started successfully."
fi

# 3. Check .env file
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        log_warn ".env file not found. Creating from .env.example..."
        cp .env.example .env
        chmod 600 .env
        log_error "Please edit .env and configure your DISCORD_TOKEN before starting!"
        echo "Run: nano .env"
        exit 1
    else
        log_error ".env and .env.example are missing!"
        exit 1
    fi
fi

# Verify DISCORD_TOKEN is set
if grep -q "your_discord_bot_token_here" .env || ! grep -q "^DISCORD_TOKEN=" .env; then
    log_error "DISCORD_TOKEN in .env is still set to placeholder or empty!"
    echo "Please edit .env: nano .env"
    exit 1
fi

chmod 600 .env
log_info "Permissions for .env secured (600)."

# 4. Build and start containers
log_info "Building and launching containers via Docker Compose..."
$SUDO docker compose down --remove-orphans || true
$SUDO docker compose up -d --build

log_success "Deployment completed successfully!"
echo ""
echo -e "${GREEN}Status check:${NC}"
$SUDO docker compose ps
echo ""
log_info "To follow live logs: docker compose logs -f discord-bot"
log_info "To stop the bot:     docker compose down"
