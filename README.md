# Polymarket BTC 15-Min Dual-Strategy Arbitrage Bot

A professional-grade, 24/7 automated trading bot for Polymarket's BTC 15-minute UP/DOWN markets. It implements two distinct strategies to maximize profit: **Pure Arbitrage** and **Temporal Arbitrage**.

## Core Strategies

### Strategy 1: Pure Arbitrage (Risk-Free)

Buy both UP and DOWN shares when their combined price is less than $1.00. Guaranteed profit regardless of outcome.

### Strategy 2: Temporal Arbitrage (High-Profit Engine)

Exploits the time lag between real-time BTC price movements on Binance and Polymarket's repricing. When BTC moves significantly but Polymarket hasn't caught up, buy the winning side at a discount.

## Features

| Feature | Description |
|---|---|
| Dual-Strategy Engine | Runs both Pure and Temporal Arbitrage simultaneously |
| 24/7 Automated Operation | Auto-discovers and transitions between 15-minute markets |
| Real-time CEX Feed | Live WebSocket feed from Binance for instant price data |
| Advanced Risk Management | Daily loss limits, max position size, single-bet limits |
| Telegram Notifications | Real-time alerts for trades, settlements, and risk warnings |
| Dry-Run Mode | Test strategies without risking real money |
| systemd Service | Auto-restart on crash, starts on boot |

## Quick Start: VPS Deployment

### Prerequisites

- Ubuntu 20.04+ or Debian 11+ VPS (DigitalOcean $4/mo, Vultr $3.5/mo, etc.)
- Python 3.10+
- A Polymarket wallet funded with USDC on Polygon

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/polymarket-bot.git
cd polymarket-bot
```

### Step 2: Run the Deployer

```bash
chmod +x deploy.sh
bash deploy.sh
```

This will:
- Install all system and Python dependencies
- Create a Python virtual environment
- Set up a systemd service for 24/7 operation
- Create the config directory structure

### Step 3: Configure Your Bot

```bash
nano config/.env
```

Fill in your details:

```ini
# Your wallet private key (REQUIRED)
POLYMARKET_PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE

# Signature type: 0=EOA, 2=GNOSIS_SAFE (if using Polymarket proxy wallet)
POLYMARKET_SIGNATURE_TYPE=2
POLYMARKET_FUNDER=0xYOUR_PROXY_WALLET_ADDRESS

# Start in simulation mode first!
DRY_RUN=true

# Strategy parameters (adjust as needed)
TARGET_PAIR_COST=0.998
TEMPORAL_ARB_CONFIDENCE_THRESHOLD=0.50
TEMPORAL_ARB_PRICE_THRESHOLD=0.45

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=true
```

### Step 4: Start in Simulation Mode

```bash
sudo systemctl start polymarket-bot
```

Monitor the logs:

```bash
tail -f logs/bot.log
```

### Step 5: Go Live

Once you're satisfied with simulation results:

1. Stop the bot: `sudo systemctl stop polymarket-bot`
2. Edit config: Set `DRY_RUN=false` in `config/.env`
3. Restart: `sudo systemctl start polymarket-bot`

## Management Commands

### Using systemd (recommended for 24/7 operation)

```bash
sudo systemctl start polymarket-bot     # Start
sudo systemctl stop polymarket-bot      # Stop
sudo systemctl restart polymarket-bot   # Restart
sudo systemctl status polymarket-bot    # Status
journalctl -u polymarket-bot -f         # System logs
```

### Using start.sh (alternative)

```bash
./start.sh start     # Start in background
./start.sh stop      # Stop
./start.sh restart   # Restart
./start.sh status    # Status + recent logs
./start.sh logs      # Follow live logs
```

## Configuration Reference

| Parameter | Default | Description |
|---|---|---|
| `POLYMARKET_PRIVATE_KEY` | (required) | Wallet private key |
| `POLYMARKET_SIGNATURE_TYPE` | `2` | 0=EOA, 2=GNOSIS_SAFE |
| `POLYMARKET_FUNDER` | | Proxy wallet address (for GNOSIS_SAFE) |
| `TARGET_PAIR_COST` | `0.998` | Max UP+DOWN cost for pure arb |
| `PURE_ARB_ORDER_SIZE` | `20` | Shares per pure arb trade |
| `TEMPORAL_ARB_ENABLED` | `true` | Enable temporal arbitrage |
| `TEMPORAL_ARB_ORDER_SIZE` | `20` | Shares per temporal arb trade |
| `TEMPORAL_ARB_CONFIDENCE_THRESHOLD` | `0.50` | Min confidence to trigger |
| `TEMPORAL_ARB_PRICE_THRESHOLD` | `0.45` | Max price to buy winning side |
| `ORDER_TYPE` | `FOK` | FOK (Fill or Kill) or GTC |
| `DRY_RUN` | `true` | Simulation mode |
| `COOLDOWN_SECONDS` | `2` | Min seconds between trades |
| `MAX_DAILY_LOSS` | `500` | Daily loss limit ($) |
| `MAX_POSITION_SIZE` | `5000` | Max total exposure ($) |
| `MAX_SINGLE_BET` | `500` | Max single trade ($) |

## Architecture

```
polymarket_bot/
├── src/
│   ├── main.py            # Main bot loop & dual-strategy engine
│   ├── config.py          # Configuration loader
│   ├── market_finder.py   # Auto-discovers 15-min markets
│   ├── trading.py         # Order execution & CLOB API
│   ├── cex_price_feed.py  # Binance WebSocket price feed
│   ├── risk_manager.py    # Risk limits & Telegram notifications
│   └── ssl_patch.py       # SSL compatibility (auto-detects)
├── config/
│   ├── .env.example       # Configuration template
│   └── .env               # Your actual config (gitignored)
├── logs/                  # Bot logs
├── data/                  # Trade history & risk state
├── deploy.sh              # One-click VPS deployer
├── start.sh               # Bot management script
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Disclaimer

Trading involves significant risk. This bot is provided as-is without warranty. Past performance is not indicative of future results. Never invest more than you are willing to lose.
