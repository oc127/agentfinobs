"""
Risk management and Telegram notification module.

Tracks P&L, enforces daily loss limits, position limits,
and sends real-time alerts via Telegram.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Record of a single trade."""
    timestamp: float
    strategy: str          # "pure_arb" or "temporal_arb"
    direction: str         # "BOTH" for pure arb, "UP"/"DOWN" for temporal
    size: float
    cost: float
    expected_payout: float
    expected_profit: float
    market_slug: str
    status: str = "open"   # "open", "won", "lost"
    actual_pnl: float = 0.0


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date_str: str
    trades_count: int = 0
    pure_arb_count: int = 0
    temporal_arb_count: int = 0
    total_invested: float = 0.0
    total_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    max_drawdown: float = 0.0
    peak_balance: float = 0.0


class RiskManager:
    """Manages risk limits and tracks trading performance."""

    def __init__(
        self,
        max_daily_loss: float = 500.0,
        max_position_size: float = 5000.0,
        max_single_bet: float = 500.0,
        stop_loss_pct: float = 5.0,
        data_dir: str = "",
    ):
        self.max_daily_loss = max_daily_loss
        self.max_position_size = max_position_size
        self.max_single_bet = max_single_bet
        self.stop_loss_pct = stop_loss_pct

        self._trades: list[TradeRecord] = []
        self._daily_stats: dict[str, DailyStats] = {}
        self._current_exposure: float = 0.0
        self._daily_pnl: float = 0.0
        self._daily_pnl_date: str = ""
        self._halted: bool = False
        self._halt_reason: str = ""

        self._data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    @property
    def current_exposure(self) -> float:
        return self._current_exposure

    @property
    def daily_pnl(self) -> float:
        today = date.today().isoformat()
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today
        return self._daily_pnl

    def check_can_trade(self, trade_cost: float) -> tuple[bool, str]:
        """Check if a new trade is allowed under risk limits."""
        if self._halted:
            return False, f"Trading halted: {self._halt_reason}"

        # Daily loss limit
        today = date.today().isoformat()
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today

        if self._daily_pnl < -self.max_daily_loss:
            self._halted = True
            self._halt_reason = f"Daily loss limit reached: ${self._daily_pnl:.2f}"
            return False, self._halt_reason

        # Single bet limit
        if trade_cost > self.max_single_bet:
            return False, f"Trade cost ${trade_cost:.2f} exceeds max single bet ${self.max_single_bet:.2f}"

        # Position size limit
        if self._current_exposure + trade_cost > self.max_position_size:
            return False, (
                f"Would exceed max position: current ${self._current_exposure:.2f} "
                f"+ new ${trade_cost:.2f} > limit ${self.max_position_size:.2f}"
            )

        return True, "OK"

    def record_trade(self, trade: TradeRecord):
        """Record a new trade."""
        self._trades.append(trade)
        self._current_exposure += trade.cost

        today = date.today().isoformat()
        if today not in self._daily_stats:
            self._daily_stats[today] = DailyStats(date_str=today)

        stats = self._daily_stats[today]
        stats.trades_count += 1
        stats.total_invested += trade.cost

        if trade.strategy == "pure_arb":
            stats.pure_arb_count += 1
        else:
            stats.temporal_arb_count += 1

        logger.info(
            f"[RISK] Trade recorded: {trade.strategy} {trade.direction} "
            f"${trade.cost:.2f} (exposure: ${self._current_exposure:.2f})"
        )

    def record_settlement(self, trade: TradeRecord, won: bool, pnl: float):
        """Record the settlement of a trade."""
        trade.status = "won" if won else "lost"
        trade.actual_pnl = pnl

        self._current_exposure = max(0, self._current_exposure - trade.cost)

        today = date.today().isoformat()
        if self._daily_pnl_date != today:
            self._daily_pnl = 0.0
            self._daily_pnl_date = today
        self._daily_pnl += pnl

        if today in self._daily_stats:
            stats = self._daily_stats[today]
            stats.total_pnl += pnl
            if won:
                stats.wins += 1
            else:
                stats.losses += 1

        logger.info(
            f"[RISK] Settlement: {'WON' if won else 'LOST'} "
            f"PnL: ${pnl:+.2f} (daily: ${self._daily_pnl:+.2f})"
        )

    def get_summary(self) -> dict:
        """Get current risk summary."""
        today = date.today().isoformat()
        stats = self._daily_stats.get(today, DailyStats(date_str=today))

        win_rate = (
            (stats.wins / (stats.wins + stats.losses) * 100)
            if (stats.wins + stats.losses) > 0
            else 0
        )

        return {
            "halted": self._halted,
            "halt_reason": self._halt_reason,
            "current_exposure": self._current_exposure,
            "daily_pnl": self.daily_pnl,
            "daily_trades": stats.trades_count,
            "daily_wins": stats.wins,
            "daily_losses": stats.losses,
            "win_rate": win_rate,
            "total_invested_today": stats.total_invested,
            "pure_arb_count": stats.pure_arb_count,
            "temporal_arb_count": stats.temporal_arb_count,
        }

    def save_state(self):
        """Save current state to disk."""
        try:
            state = {
                "trades": [
                    {
                        "timestamp": t.timestamp,
                        "strategy": t.strategy,
                        "direction": t.direction,
                        "size": t.size,
                        "cost": t.cost,
                        "expected_payout": t.expected_payout,
                        "expected_profit": t.expected_profit,
                        "market_slug": t.market_slug,
                        "status": t.status,
                        "actual_pnl": t.actual_pnl,
                    }
                    for t in self._trades[-100:]  # Keep last 100 trades
                ],
                "daily_pnl": self._daily_pnl,
                "daily_pnl_date": self._daily_pnl_date,
                "current_exposure": self._current_exposure,
            }
            path = self._data_dir / "risk_state.json"
            path.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save risk state: {e}")

    def reset_daily(self):
        """Reset daily counters (called at midnight)."""
        self._daily_pnl = 0.0
        self._daily_pnl_date = date.today().isoformat()
        self._halted = False
        self._halt_reason = ""
        logger.info("[RISK] Daily counters reset")


class TelegramNotifier:
    """Send notifications via Telegram bot."""

    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled and bool(bot_token) and bool(chat_id)
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, message: str, parse_mode: str = "HTML"):
        """Send a message via Telegram."""
        if not self.enabled:
            return

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": parse_mode,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.warning(f"Telegram send failed: {e}")

    async def notify_trade(self, trade: TradeRecord):
        """Send trade notification."""
        emoji = "\U0001f3af" if trade.strategy == "pure_arb" else "\u26a1"
        msg = (
            f"{emoji} <b>New Trade</b>\n"
            f"Strategy: {trade.strategy}\n"
            f"Direction: {trade.direction}\n"
            f"Size: {trade.size:.0f} shares\n"
            f"Cost: ${trade.cost:.2f}\n"
            f"Expected Profit: ${trade.expected_profit:.2f}\n"
            f"Market: {trade.market_slug}"
        )
        await self.send(msg)

    async def notify_settlement(self, trade: TradeRecord, won: bool):
        """Send settlement notification."""
        emoji = "\u2705" if won else "\u274c"
        msg = (
            f"{emoji} <b>Settlement</b>\n"
            f"Result: {'WON' if won else 'LOST'}\n"
            f"PnL: ${trade.actual_pnl:+.2f}\n"
            f"Market: {trade.market_slug}"
        )
        await self.send(msg)

    async def notify_risk_alert(self, message: str):
        """Send risk alert."""
        msg = f"\u26a0\ufe0f <b>Risk Alert</b>\n{message}"
        await self.send(msg)

    async def notify_daily_summary(self, summary: dict):
        """Send daily summary."""
        msg = (
            f"\U0001f4ca <b>Daily Summary</b>\n"
            f"Trades: {summary['daily_trades']}\n"
            f"Wins: {summary['daily_wins']} | Losses: {summary['daily_losses']}\n"
            f"Win Rate: {summary['win_rate']:.1f}%\n"
            f"Daily PnL: ${summary['daily_pnl']:+.2f}\n"
            f"Total Invested: ${summary['total_invested_today']:.2f}\n"
            f"Pure Arb: {summary['pure_arb_count']} | Temporal: {summary['temporal_arb_count']}"
        )
        await self.send(msg)
