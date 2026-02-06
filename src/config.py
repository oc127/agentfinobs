"""
Configuration module for the Polymarket BTC 15-Min Arbitrage Bot.
Loads settings from environment variables and .env file.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / "config" / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)
else:
    # Fallback: try project root
    load_dotenv(_project_root / ".env", override=False)


def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def _float(val: str, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _int(val: str, default: int = 0) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


@dataclass
class Settings:
    # --- Polymarket Wallet & API ---
    private_key: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    signature_type: int = _int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2"))
    funder: str = os.getenv("POLYMARKET_FUNDER", "")
    market_slug: str = os.getenv("POLYMARKET_MARKET_SLUG", "")

    # --- Backup API Credentials (from website) ---
    api_key: str = os.getenv("POLYMARKET_API_KEY", "")
    api_secret: str = os.getenv("POLYMARKET_API_SECRET", "")
    api_passphrase: str = os.getenv("POLYMARKET_API_PASSPHRASE", "")

    # --- Strategy 1: Pure Arbitrage ---
    target_pair_cost: float = _float(os.getenv("TARGET_PAIR_COST", "0.993"))
    pure_arb_order_size: float = _float(os.getenv("PURE_ARB_ORDER_SIZE", "50"))

    # --- Strategy 2: Temporal Arbitrage ---
    temporal_arb_enabled: bool = _bool(os.getenv("TEMPORAL_ARB_ENABLED", "true"))
    temporal_arb_order_size: float = _float(os.getenv("TEMPORAL_ARB_ORDER_SIZE", "100"))
    temporal_arb_confidence_threshold: float = _float(
        os.getenv("TEMPORAL_ARB_CONFIDENCE_THRESHOLD", "0.70")
    )
    temporal_arb_price_threshold: float = _float(
        os.getenv("TEMPORAL_ARB_PRICE_THRESHOLD", "0.55")
    )

    # --- CEX Price Feed ---
    binance_enabled: bool = _bool(os.getenv("BINANCE_ENABLED", "true"))

    # --- General ---
    order_type: str = os.getenv("ORDER_TYPE", "FOK").upper()
    dry_run: bool = _bool(os.getenv("DRY_RUN", "true"))
    cooldown_seconds: float = _float(os.getenv("COOLDOWN_SECONDS", "5"))
    use_wss: bool = _bool(os.getenv("USE_WSS", "true"))
    ws_url: str = os.getenv(
        "POLYMARKET_WS_URL", "wss://ws-subscriptions-clob.polymarket.com"
    )
    sim_balance: float = _float(os.getenv("SIM_BALANCE", "1000"))

    # --- Risk Management ---
    max_daily_loss: float = _float(os.getenv("MAX_DAILY_LOSS", "500"))
    max_position_size: float = _float(os.getenv("MAX_POSITION_SIZE", "5000"))
    max_single_bet: float = _float(os.getenv("MAX_SINGLE_BET", "500"))
    stop_loss_pct: float = _float(os.getenv("STOP_LOSS_PCT", "5.0"))

    # --- Telegram ---
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_enabled: bool = _bool(os.getenv("TELEGRAM_ENABLED", "false"))

    # --- Logging ---
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    verbose: bool = _bool(os.getenv("VERBOSE", "false"))


def load_settings() -> Settings:
    return Settings()
