#!/bin/bash
# ============================================================
# Polymarket BTC 15-Min Arbitrage Bot - Management Script
# ============================================================

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$BOT_DIR/bot.pid"
LOG_FILE="$BOT_DIR/logs/bot.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo -e "${YELLOW}Bot is already running (PID: $(cat "$PID_FILE"))${NC}"
        return 1
    fi

    echo -e "${CYAN}Starting Polymarket Arbitrage Bot...${NC}"
    mkdir -p "$BOT_DIR/logs" "$BOT_DIR/data"

    cd "$BOT_DIR"
    nohup python3 -m src.main >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    sleep 2
    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo -e "${GREEN}Bot started successfully (PID: $(cat "$PID_FILE"))${NC}"
        echo -e "Log: $LOG_FILE"
    else
        echo -e "${RED}Bot failed to start. Check logs: $LOG_FILE${NC}"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Bot is not running (no PID file)${NC}"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${CYAN}Stopping bot (PID: $PID)...${NC}"
        kill "$PID"
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            kill -9 "$PID"
        fi
        echo -e "${GREEN}Bot stopped${NC}"
    else
        echo -e "${YELLOW}Bot process not found${NC}"
    fi
    rm -f "$PID_FILE"
}

restart() {
    stop
    sleep 1
    start
}

status() {
    echo -e "${CYAN}=== Polymarket Arbitrage Bot Status ===${NC}"
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo -e "Status: ${GREEN}RUNNING${NC} (PID: $(cat "$PID_FILE"))"
    else
        echo -e "Status: ${RED}STOPPED${NC}"
    fi

    if [ -f "$LOG_FILE" ]; then
        echo -e "\n${CYAN}--- Last 20 log lines ---${NC}"
        tail -20 "$LOG_FILE"
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo -e "${YELLOW}No log file found${NC}"
    fi
}

case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    logs)    logs ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start   - Start the bot in background"
        echo "  stop    - Stop the bot"
        echo "  restart - Restart the bot"
        echo "  status  - Show bot status and recent logs"
        echo "  logs    - Follow log output in real-time"
        exit 1
        ;;
esac
