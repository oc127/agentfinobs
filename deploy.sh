#!/bin/bash
# ============================================================
# Polymarket BTC 15-Min Arbitrage Bot - One-Click VPS Deployer
# ============================================================
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/<YOUR_REPO>/main/deploy.sh | bash
#   OR
#   bash deploy.sh
#
# Supports: Ubuntu 20.04+, Debian 11+
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Polymarket BTC 15-Min Arbitrage Bot - VPS Deployer     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: System Dependencies ──────────────────────────────
echo -e "${CYAN}[1/6] Installing system dependencies...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git screen > /dev/null 2>&1
echo -e "${GREEN}  ✓ System dependencies installed${NC}"

# ── Step 2: Setup Project Directory ──────────────────────────
BOT_DIR="$HOME/polymarket_bot"
echo -e "${CYAN}[2/6] Setting up project directory: $BOT_DIR${NC}"

if [ -d "$BOT_DIR" ]; then
    echo -e "${YELLOW}  Directory already exists. Backing up config...${NC}"
    [ -f "$BOT_DIR/config/.env" ] && cp "$BOT_DIR/config/.env" "/tmp/.env.backup.$(date +%s)"
fi

# If running from the repo directory, just use current dir
if [ -f "$(pwd)/src/main.py" ]; then
    BOT_DIR="$(pwd)"
    echo -e "${GREEN}  ✓ Using current directory${NC}"
else
    mkdir -p "$BOT_DIR"
    echo -e "${GREEN}  ✓ Directory ready${NC}"
fi

# ── Step 3: Python Virtual Environment ───────────────────────
echo -e "${CYAN}[3/6] Setting up Python virtual environment...${NC}"
cd "$BOT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "${GREEN}  ✓ Python dependencies installed${NC}"

# ── Step 4: Configuration ────────────────────────────────────
echo -e "${CYAN}[4/6] Configuring bot...${NC}"

mkdir -p config logs data

if [ ! -f "config/.env" ]; then
    if [ -f "config/.env.example" ]; then
        cp config/.env.example config/.env
        echo -e "${YELLOW}  ⚠ Created config/.env from template${NC}"
        echo -e "${YELLOW}  ⚠ You MUST edit config/.env with your private key!${NC}"
    else
        echo -e "${RED}  ✗ No .env.example found. Please create config/.env manually.${NC}"
    fi
else
    echo -e "${GREEN}  ✓ config/.env already exists${NC}"
fi

# ── Step 5: Create systemd service ───────────────────────────
echo -e "${CYAN}[5/6] Setting up systemd service for 24/7 operation...${NC}"

SERVICE_FILE="/etc/systemd/system/polymarket-bot.service"
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Polymarket BTC 15-Min Arbitrage Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python3 -m src.main
Restart=always
RestartSec=10
StandardOutput=append:$BOT_DIR/logs/bot.log
StandardError=append:$BOT_DIR/logs/bot.log

# Environment
Environment=PYTHONUNBUFFERED=1

# Resource limits
LimitNOFILE=65535
MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable polymarket-bot
echo -e "${GREEN}  ✓ systemd service installed and enabled${NC}"

# ── Step 6: Final Instructions ───────────────────────────────
echo -e "${CYAN}[6/6] Setup complete!${NC}"
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    SETUP COMPLETE!                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo ""
echo -e "  1. ${YELLOW}Edit your config:${NC}"
echo -e "     nano $BOT_DIR/config/.env"
echo ""
echo -e "  2. ${YELLOW}Start the bot:${NC}"
echo -e "     sudo systemctl start polymarket-bot"
echo ""
echo -e "  3. ${YELLOW}Check status:${NC}"
echo -e "     sudo systemctl status polymarket-bot"
echo ""
echo -e "  4. ${YELLOW}View live logs:${NC}"
echo -e "     tail -f $BOT_DIR/logs/bot.log"
echo ""
echo -e "  5. ${YELLOW}Stop the bot:${NC}"
echo -e "     sudo systemctl stop polymarket-bot"
echo ""
echo -e "${CYAN}Management commands:${NC}"
echo -e "  ./start.sh start    - Start with start.sh (alternative)"
echo -e "  ./start.sh stop     - Stop the bot"
echo -e "  ./start.sh status   - Check status"
echo -e "  ./start.sh logs     - Follow logs"
echo ""
echo -e "${RED}⚠ IMPORTANT: Make sure config/.env has your private key set!${NC}"
echo -e "${RED}⚠ Start with DRY_RUN=true first to test!${NC}"
