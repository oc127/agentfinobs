"""
Polymarket BTC 15-Minute Dual-Strategy Arbitrage Bot

Runs 24/7, automatically discovering new markets every 15 minutes.

Strategy 1 - Pure Arbitrage:
  Buy both UP + DOWN when combined cost < $1.00.
  Guaranteed profit regardless of outcome.

Strategy 2 - Temporal Arbitrage:
  Monitor real-time BTC price on Binance.
  When BTC moves significantly but Polymarket hasn't repriced yet,
  buy the correct side at a discount.
  This is how the $313 -> $414K bot works.
"""

# SSL patch must be imported first to fix sandbox certificate issues
from . import ssl_patch  # noqa: F401

import asyncio
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Settings, load_settings
from .market_finder import (
    get_active_btc_15m_slug,
    fetch_market_from_slug,
    get_time_remaining,
    get_market_timestamps,
    BTC_15M_WINDOW,
)
from .trading import (
    get_client,
    get_balance,
    get_order_book,
    compute_buy_fill,
    place_order,
    place_orders_fast,
    extract_order_id,
    wait_for_terminal_order,
    cancel_orders,
)
from .cex_price_feed import BinancePriceFeed, MomentumSignal
from .risk_manager import RiskManager, TradeRecord, TelegramNotifier

# Agent Financial Observability
from agentfinobs import ObservabilityStack, PaymentRail

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).resolve().parent.parent / "logs" / "bot.log",
            mode="a",
        ),
    ],
)
logger = logging.getLogger("polymarket_bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)


class PolymarketArbBot:
    """Dual-strategy Polymarket BTC 15-minute arbitrage bot."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None  # Lazy init (only when not dry_run)

        # CEX price feed
        self.price_feed = BinancePriceFeed(history_seconds=1200)

        # Risk management
        self.risk_manager = RiskManager(
            max_daily_loss=settings.max_daily_loss,
            max_position_size=settings.max_position_size,
            max_single_bet=settings.max_single_bet,
            stop_loss_pct=settings.stop_loss_pct,
            data_dir=str(Path(__file__).resolve().parent.parent / "data"),
        )

        # Telegram notifications
        self.notifier = TelegramNotifier(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            enabled=settings.telegram_enabled,
        )

        # Agent Financial Observability
        self.obs = ObservabilityStack.create(
            agent_id="polymarket-arb-bot",
            budget_rules=[
                {"name": "hourly", "max_amount": settings.max_single_bet * 5,
                 "window_seconds": 3600, "severity": "warning"},
                {"name": "daily", "max_amount": settings.max_position_size,
                 "window_seconds": 86400, "severity": "critical",
                 "halt_on_breach": True},
            ],
            total_budget=settings.sim_balance if settings.dry_run else settings.max_position_size,
            persist_dir=str(Path(__file__).resolve().parent.parent / "data" / "obs"),
            dashboard_port=9400,
        )

        # Current market state
        self.market_slug: Optional[str] = None
        self.market_id: Optional[str] = None
        self.yes_token_id: Optional[str] = None
        self.no_token_id: Optional[str] = None
        self.market_end_ts: Optional[int] = None

        # Statistics
        self.total_scans = 0
        self.pure_arb_opportunities = 0
        self.temporal_arb_opportunities = 0
        self.trades_executed = 0
        self.session_start = time.time()

        # Simulation tracking
        self.sim_balance = settings.sim_balance
        self.sim_start_balance = settings.sim_balance
        self.sim_trades: list[dict] = []

        # Cooldown
        self._last_trade_ts = 0.0

    def _init_client(self):
        """Initialize the Polymarket CLOB client (only for live trading)."""
        if not self.settings.dry_run and self.client is None:
            self.client = get_client(self.settings)

    def _init_client_for_reading(self):
        """Initialize client for reading order books (works in dry_run too)."""
        if self.client is None:
            self.client = get_client(self.settings)

    def _load_market(self, slug: str):
        """Load market details from a slug."""
        info = fetch_market_from_slug(slug)
        self.market_slug = slug
        self.market_id = info["market_id"]
        self.yes_token_id = info["yes_token_id"]
        self.no_token_id = info["no_token_id"]

        start_ts, end_ts = get_market_timestamps(slug)
        self.market_end_ts = end_ts

        logger.info(f"Loaded market: {slug}")
        logger.info(f"  Market ID: {self.market_id}")
        logger.info(f"  UP Token:  {self.yes_token_id[:16]}...")
        logger.info(f"  DOWN Token: {self.no_token_id[:16]}...")
        logger.info(f"  Closes at: {datetime.fromtimestamp(end_ts).strftime('%H:%M:%S') if end_ts else 'Unknown'}")

    def _is_market_closed(self) -> bool:
        if self.market_end_ts is None:
            return False
        return int(time.time()) >= self.market_end_ts

    def _get_time_remaining_str(self) -> str:
        if self.market_slug:
            return get_time_remaining(self.market_slug)
        return "Unknown"

    # ── Strategy 1: Pure Arbitrage ──────────────────────────────────

    def check_pure_arbitrage(self, up_book: dict, down_book: dict) -> Optional[dict]:
        """
        Check if pure arbitrage opportunity exists.
        Buy both UP + DOWN when total cost < $1.00.
        """
        asks_up = up_book.get("asks", [])
        asks_down = down_book.get("asks", [])

        fill_up = compute_buy_fill(asks_up, self.settings.pure_arb_order_size)
        fill_down = compute_buy_fill(asks_down, self.settings.pure_arb_order_size)

        if not fill_up or not fill_down:
            return None

        limit_price_up = fill_up["worst"]
        limit_price_down = fill_down["worst"]
        if limit_price_up is None or limit_price_down is None:
            return None

        total_cost = limit_price_up + limit_price_down

        if total_cost <= self.settings.target_pair_cost:
            profit = 1.0 - total_cost
            profit_pct = (profit / total_cost) * 100 if total_cost > 0 else 0
            size = self.settings.pure_arb_order_size
            investment = total_cost * size
            expected_payout = 1.0 * size
            expected_profit = expected_payout - investment

            return {
                "strategy": "pure_arb",
                "price_up": limit_price_up,
                "price_down": limit_price_down,
                "total_cost": total_cost,
                "profit_per_share": profit,
                "profit_pct": profit_pct,
                "order_size": size,
                "total_investment": investment,
                "expected_payout": expected_payout,
                "expected_profit": expected_profit,
                "vwap_up": fill_up.get("vwap"),
                "vwap_down": fill_down.get("vwap"),
            }
        return None

    # ── Strategy 2: Temporal Arbitrage ──────────────────────────────

    def check_temporal_arbitrage(
        self, up_book: dict, down_book: dict, momentum: Optional[MomentumSignal]
    ) -> Optional[dict]:
        """
        Check if temporal arbitrage opportunity exists.

        Logic:
        - Binance shows BTC has moved significantly (e.g., +0.15%)
        - Polymarket UP/DOWN prices haven't caught up yet
        - Buy the winning side at a discount
        """
        if not self.settings.temporal_arb_enabled:
            return None

        if momentum is None:
            return None

        if momentum.confidence < self.settings.temporal_arb_confidence_threshold:
            return None

        # Determine which side to buy
        if momentum.direction == "UP":
            target_token = self.yes_token_id
            target_book = up_book
            side_name = "UP"
        else:
            target_token = self.no_token_id
            target_book = down_book
            side_name = "DOWN"

        best_ask = target_book.get("best_ask")
        if best_ask is None:
            return None

        # The key insight: if the market hasn't repriced yet,
        # the winning side should still be cheap (< threshold)
        if best_ask > self.settings.temporal_arb_price_threshold:
            return None  # Market has already repriced

        # Check if we can fill our order size
        asks = target_book.get("asks", [])
        fill = compute_buy_fill(asks, self.settings.temporal_arb_order_size)
        if not fill:
            return None

        size = self.settings.temporal_arb_order_size
        cost = fill["cost"]
        # Expected payout: if we're right, each share pays $1.00
        expected_payout = size * 1.0
        expected_profit = expected_payout - cost

        return {
            "strategy": "temporal_arb",
            "direction": side_name,
            "token_id": target_token,
            "price": fill["worst"],
            "vwap": fill["vwap"],
            "order_size": size,
            "total_investment": cost,
            "expected_payout": expected_payout,
            "expected_profit": expected_profit,
            "confidence": momentum.confidence,
            "btc_change_pct": momentum.price_change_pct,
            "btc_price": momentum.current_price,
        }

    # ── Trade Execution ─────────────────────────────────────────────

    def execute_pure_arbitrage(self, opp: dict):
        """Execute a pure arbitrage trade (buy both sides)."""
        now = time.time()
        if (now - self._last_trade_ts) < self.settings.cooldown_seconds:
            logger.info("Cooldown active, skipping")
            return
        self._last_trade_ts = now

        # Risk check
        can_trade, reason = self.risk_manager.check_can_trade(opp["total_investment"])
        if not can_trade:
            logger.warning(f"Risk check failed: {reason}")
            return

        logger.info("=" * 70)
        logger.info("PURE ARBITRAGE OPPORTUNITY")
        logger.info("=" * 70)
        logger.info(f"UP price:     ${opp['price_up']:.4f}")
        logger.info(f"DOWN price:   ${opp['price_down']:.4f}")
        logger.info(f"Total cost:   ${opp['total_cost']:.4f}")
        logger.info(f"Profit/share: ${opp['profit_per_share']:.4f} ({opp['profit_pct']:.2f}%)")
        logger.info(f"Order size:   {opp['order_size']:.0f} shares each side")
        logger.info(f"Investment:   ${opp['total_investment']:.2f}")
        logger.info(f"Exp. profit:  ${opp['expected_profit']:.2f}")
        logger.info("=" * 70)

        trade = TradeRecord(
            timestamp=now,
            strategy="pure_arb",
            direction="BOTH",
            size=opp["order_size"],
            cost=opp["total_investment"],
            expected_payout=opp["expected_payout"],
            expected_profit=opp["expected_profit"],
            market_slug=self.market_slug or "",
        )

        if self.settings.dry_run:
            logger.info("[SIM] Pure arbitrage executed (simulation)")
            if self.sim_balance < opp["total_investment"]:
                logger.warning(f"[SIM] Insufficient balance: ${self.sim_balance:.2f}")
                return
            self.sim_balance -= opp["total_investment"]
            # In pure arb, we always win
            self.sim_balance += opp["expected_payout"]
            self.sim_trades.append(opp)
            self.risk_manager.record_trade(trade)
            self.risk_manager.record_settlement(trade, won=True, pnl=opp["expected_profit"])
            self.trades_executed += 1
            self.pure_arb_opportunities += 1

            # Observability: track + settle
            otx = self.obs.track(
                amount=opp["total_investment"],
                task_id=f"pure_arb:{self.market_slug}",
                rail=PaymentRail.POLYMARKET_CLOB,
                counterparty="polymarket",
                description=f"Pure arb BOTH {opp['order_size']:.0f}sh @${opp['total_cost']:.4f}",
                tags={"strategy": "pure_arb", "market": self.market_slug or ""},
            )
            self.obs.settle(otx.tx_id, revenue=opp["expected_payout"])

            logger.info(f"[SIM] Balance: ${self.sim_balance:.2f} (+${opp['expected_profit']:.2f})")
            asyncio.ensure_future(self.notifier.notify_trade(trade))
            return

        # Live trading
        self._init_client()
        try:
            orders = [
                {"side": "BUY", "token_id": self.yes_token_id, "price": opp["price_up"], "size": opp["order_size"]},
                {"side": "BUY", "token_id": self.no_token_id, "price": opp["price_down"], "size": opp["order_size"]},
            ]

            results = place_orders_fast(self.settings, orders, order_type=self.settings.order_type)

            order_ids = [extract_order_id(r) if isinstance(r, dict) else None for r in (results or [])]

            if not order_ids[0] or not order_ids[1]:
                raise RuntimeError(f"Could not extract order IDs: {results}")

            up_state = wait_for_terminal_order(self.settings, order_ids[0], requested_size=opp["order_size"])
            down_state = wait_for_terminal_order(self.settings, order_ids[1], requested_size=opp["order_size"])

            if up_state.get("filled") and down_state.get("filled"):
                logger.info("BOTH LEGS FILLED - Pure arbitrage executed!")
                self.risk_manager.record_trade(trade)
                self.trades_executed += 1
                self.pure_arb_opportunities += 1
                asyncio.ensure_future(self.notifier.notify_trade(trade))
            else:
                # Partial fill handling
                logger.warning("Partial fill detected, attempting cleanup...")
                try:
                    cancel_orders(self.settings, [oid for oid in order_ids if oid])
                except Exception:
                    pass

                # Unwind filled leg
                for i, (state, token_id) in enumerate(
                    [(up_state, self.yes_token_id), (down_state, self.no_token_id)]
                ):
                    if state.get("filled"):
                        book = get_order_book(self.client, token_id)
                        best_bid = book.get("best_bid")
                        if best_bid:
                            place_order(
                                self.settings,
                                side="SELL",
                                token_id=token_id,
                                price=best_bid,
                                size=opp["order_size"],
                                tif="FAK",
                            )

        except Exception as e:
            logger.error(f"Pure arbitrage execution failed: {e}")

    def execute_temporal_arbitrage(self, opp: dict):
        """Execute a temporal arbitrage trade (buy one side)."""
        now = time.time()
        if (now - self._last_trade_ts) < self.settings.cooldown_seconds:
            logger.info("Cooldown active, skipping")
            return
        self._last_trade_ts = now

        # Risk check
        can_trade, reason = self.risk_manager.check_can_trade(opp["total_investment"])
        if not can_trade:
            logger.warning(f"Risk check failed: {reason}")
            return

        logger.info("=" * 70)
        logger.info("TEMPORAL ARBITRAGE OPPORTUNITY")
        logger.info("=" * 70)
        logger.info(f"Direction:    {opp['direction']}")
        logger.info(f"BTC change:   {opp['btc_change_pct']:+.3f}%")
        logger.info(f"BTC price:    ${opp['btc_price']:,.2f}")
        logger.info(f"Confidence:   {opp['confidence']:.0%}")
        logger.info(f"Buy price:    ${opp['price']:.4f}")
        logger.info(f"Order size:   {opp['order_size']:.0f} shares")
        logger.info(f"Investment:   ${opp['total_investment']:.2f}")
        logger.info(f"Exp. profit:  ${opp['expected_profit']:.2f}")
        logger.info("=" * 70)

        trade = TradeRecord(
            timestamp=now,
            strategy="temporal_arb",
            direction=opp["direction"],
            size=opp["order_size"],
            cost=opp["total_investment"],
            expected_payout=opp["expected_payout"],
            expected_profit=opp["expected_profit"],
            market_slug=self.market_slug or "",
        )

        if self.settings.dry_run:
            logger.info(f"[SIM] Temporal arbitrage: BUY {opp['direction']} (simulation)")
            if self.sim_balance < opp["total_investment"]:
                logger.warning(f"[SIM] Insufficient balance: ${self.sim_balance:.2f}")
                return
            self.sim_balance -= opp["total_investment"]
            self.sim_trades.append(opp)
            self.risk_manager.record_trade(trade)
            self.trades_executed += 1
            self.temporal_arb_opportunities += 1

            # Observability: track (settlement happens when 15-min window closes)
            self.obs.track(
                amount=opp["total_investment"],
                task_id=f"temporal_arb:{self.market_slug}",
                rail=PaymentRail.POLYMARKET_CLOB,
                counterparty="polymarket",
                description=f"Temporal arb BUY {opp['direction']} {opp['order_size']:.0f}sh @${opp['price']:.4f}",
                tags={"strategy": "temporal_arb", "direction": opp["direction"],
                      "market": self.market_slug or "",
                      "confidence": f"{opp['confidence']:.2f}"},
            )

            logger.info(f"[SIM] Balance: ${self.sim_balance:.2f} (awaiting settlement)")
            asyncio.ensure_future(self.notifier.notify_trade(trade))
            return

        # Live trading
        self._init_client()
        try:
            result = place_order(
                self.settings,
                side="BUY",
                token_id=opp["token_id"],
                price=opp["price"],
                size=opp["order_size"],
                tif=self.settings.order_type,
            )

            order_id = extract_order_id(result)
            if order_id:
                state = wait_for_terminal_order(
                    self.settings, order_id, requested_size=opp["order_size"]
                )
                if state.get("filled"):
                    logger.info(f"Temporal arbitrage executed: BUY {opp['direction']}")
                    self.risk_manager.record_trade(trade)
                    self.trades_executed += 1
                    self.temporal_arb_opportunities += 1
                    asyncio.ensure_future(self.notifier.notify_trade(trade))
                else:
                    logger.warning(f"Order not filled: {state}")
            else:
                logger.error(f"Could not extract order ID: {result}")

        except Exception as e:
            logger.error(f"Temporal arbitrage execution failed: {e}")

    # ── Main Loop ───────────────────────────────────────────────────

    async def scan_once(self) -> dict:
        """
        Perform one scan cycle.
        Returns dict with scan results.
        """
        self.total_scans += 1

        if not self.market_slug or self._is_market_closed():
            return {"status": "market_closed"}

        # Get order books (always use real data when possible)
        try:
            self._init_client_for_reading()
            up_book = get_order_book(self.client, self.yes_token_id)
            down_book = get_order_book(self.client, self.no_token_id)
        except Exception as e:
            if self.settings.dry_run:
                logger.debug(f"Using simulated order books: {e}")
                up_book = self._simulate_order_book()
                down_book = self._simulate_order_book()
            else:
                raise

        if not up_book or not down_book:
            return {"status": "no_books"}

        result = {
            "status": "scanned",
            "up_best_ask": up_book.get("best_ask"),
            "down_best_ask": down_book.get("best_ask"),
            "time_remaining": self._get_time_remaining_str(),
        }

        # Strategy 1: Pure Arbitrage
        pure_opp = self.check_pure_arbitrage(up_book, down_book)
        if pure_opp:
            result["pure_arb"] = pure_opp
            self.execute_pure_arbitrage(pure_opp)

        # Strategy 2: Temporal Arbitrage
        if self.settings.temporal_arb_enabled:
            momentum = self.price_feed.get_multi_timeframe_signal()
            temporal_opp = self.check_temporal_arbitrage(up_book, down_book, momentum)
            if temporal_opp:
                result["temporal_arb"] = temporal_opp
                self.execute_temporal_arbitrage(temporal_opp)
            if momentum:
                result["momentum"] = {
                    "direction": momentum.direction,
                    "confidence": momentum.confidence,
                    "change_pct": momentum.price_change_pct,
                }

        return result

    def _simulate_order_book(self) -> dict:
        """Generate a simulated order book for dry-run mode."""
        import random

        mid = 0.50
        spread = random.uniform(0.01, 0.04)
        best_bid = round(mid - spread / 2, 4)
        best_ask = round(mid + spread / 2, 4)

        asks = [(best_ask, random.uniform(50, 500))]
        for i in range(5):
            asks.append((round(best_ask + 0.01 * (i + 1), 4), random.uniform(20, 200)))

        bids = [(best_bid, random.uniform(50, 500))]
        for i in range(5):
            bids.append((round(best_bid - 0.01 * (i + 1), 4), random.uniform(20, 200)))

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "bid_size": asks[0][1],
            "ask_size": asks[0][1],
            "bids": bids,
            "asks": asks,
        }

    async def _handle_market_transition(self):
        """Handle transition between 15-minute markets."""
        logger.info("\nMarket closed! Searching for next market...")

        # Show summary for the closed market
        self._show_market_summary()

        # Wait a bit for the new market to appear
        for attempt in range(12):  # Try for up to 60 seconds
            try:
                new_slug = get_active_btc_15m_slug()
                if new_slug != self.market_slug:
                    logger.info(f"New market found: {new_slug}")
                    self._load_market(new_slug)

                    # Reset window start price for temporal arbitrage
                    if self.price_feed.current_price:
                        self.price_feed.set_window_start()

                    return True
            except Exception as e:
                logger.debug(f"Market search attempt {attempt + 1}: {e}")

            await asyncio.sleep(5)

        logger.warning("Could not find next market after 60s, retrying...")
        return False

    def _show_market_summary(self):
        """Show summary for the current market."""
        logger.info("=" * 70)
        logger.info(f"MARKET SUMMARY: {self.market_slug}")
        logger.info("=" * 70)
        logger.info(f"Total scans:         {self.total_scans}")
        logger.info(f"Pure arb trades:     {self.pure_arb_opportunities}")
        logger.info(f"Temporal arb trades: {self.temporal_arb_opportunities}")
        logger.info(f"Total trades:        {self.trades_executed}")
        if self.settings.dry_run:
            pnl = self.sim_balance - self.sim_start_balance
            logger.info(f"[SIM] Start balance: ${self.sim_start_balance:.2f}")
            logger.info(f"[SIM] Current:       ${self.sim_balance:.2f}")
            logger.info(f"[SIM] PnL:           ${pnl:+.2f}")
        risk_summary = self.risk_manager.get_summary()
        logger.info(f"Daily PnL:           ${risk_summary['daily_pnl']:+.2f}")

        # Observability metrics
        snap = self.obs.snapshot()
        if snap.tx_count > 0:
            logger.info(f"[OBS] Txs tracked:   {snap.tx_count}")
            logger.info(f"[OBS] Total spent:   ${snap.total_spent:.2f}")
            logger.info(f"[OBS] Total revenue: ${snap.total_revenue:.2f}")
            logger.info(f"[OBS] ROI:           {snap.roi_pct:.1f}%" if snap.roi_pct is not None else "[OBS] ROI: N/A")
            logger.info(f"[OBS] Burn rate:     ${snap.burn_rate_per_hour:.2f}/hour")

        logger.info("=" * 70)

    async def run(self):
        """Main bot loop - runs 24/7."""
        logger.info("=" * 70)
        logger.info("  POLYMARKET BTC 15-MIN DUAL-STRATEGY ARBITRAGE BOT")
        logger.info("=" * 70)
        logger.info(f"Mode:              {'SIMULATION' if self.settings.dry_run else 'LIVE TRADING'}")
        logger.info(f"Pure Arb:          threshold=${self.settings.target_pair_cost:.3f}, size={self.settings.pure_arb_order_size:.0f}")
        logger.info(f"Temporal Arb:      {'ENABLED' if self.settings.temporal_arb_enabled else 'DISABLED'}")
        if self.settings.temporal_arb_enabled:
            logger.info(f"  Confidence:      {self.settings.temporal_arb_confidence_threshold:.0%}")
            logger.info(f"  Price threshold: ${self.settings.temporal_arb_price_threshold:.2f}")
            logger.info(f"  Order size:      {self.settings.temporal_arb_order_size:.0f}")
        logger.info(f"Risk limits:       daily_loss=${self.settings.max_daily_loss:.0f}, max_bet=${self.settings.max_single_bet:.0f}")
        logger.info(f"Observability:     http://localhost:9400")
        if self.settings.dry_run:
            logger.info(f"Sim balance:       ${self.sim_balance:.2f}")

        # Show real balance
        try:
            real_balance = get_balance(self.settings)
            logger.info(f"Real USDC balance: ${real_balance:,.2f}")
        except Exception:
            pass
        logger.info("=" * 70)

        # Start Binance price feed
        if self.settings.temporal_arb_enabled and self.settings.binance_enabled:
            logger.info("Starting Binance BTC price feed...")
            price_task = asyncio.create_task(self.price_feed.start_websocket())

            # Wait for initial price
            for _ in range(50):
                if self.price_feed.current_price:
                    break
                await asyncio.sleep(0.2)

            if self.price_feed.current_price:
                logger.info(f"BTC price feed active: ${self.price_feed.current_price:,.2f}")
            else:
                # Fallback to REST
                logger.info("WebSocket not ready, fetching via REST...")
                await self.price_feed.fetch_current_price()
                if self.price_feed.current_price:
                    logger.info(f"BTC price (REST): ${self.price_feed.current_price:,.2f}")
                else:
                    logger.warning("Could not get BTC price; temporal arb will be limited")

        # Find initial market
        try:
            slug = get_active_btc_15m_slug()
            self._load_market(slug)
            if self.price_feed.current_price:
                self.price_feed.set_window_start()
        except Exception as e:
            logger.error(f"Could not find initial market: {e}")
            logger.info("Will retry in 30 seconds...")
            await asyncio.sleep(30)

        # Main loop
        scan_interval = 3  # seconds between scans (fast for temporal arb)
        logger.info(f"\nStarting main loop (scan interval: {scan_interval}s)...\n")

        try:
            while True:
                # Check if market is closed
                if self._is_market_closed():
                    success = await self._handle_market_transition()
                    if not success:
                        await asyncio.sleep(10)
                        continue

                # Check risk limits
                if self.risk_manager.is_halted:
                    logger.warning(f"Trading halted: {self.risk_manager.halt_reason}")
                    await asyncio.sleep(60)
                    continue

                # Perform scan
                try:
                    result = await self.scan_once()

                    # Log status
                    time_rem = result.get("time_remaining", "?")
                    up_ask = result.get("up_best_ask")
                    down_ask = result.get("down_best_ask")

                    if up_ask and down_ask:
                        total = up_ask + down_ask
                        momentum_str = ""
                        if "momentum" in result:
                            m = result["momentum"]
                            momentum_str = (
                                f" | BTC: {m['direction']} {m['change_pct']:+.3f}% "
                                f"(conf: {m['confidence']:.0%})"
                            )

                        logger.info(
                            f"[Scan #{self.total_scans}] "
                            f"UP=${up_ask:.4f} + DOWN=${down_ask:.4f} = ${total:.4f} "
                            f"[{time_rem}]{momentum_str}"
                        )

                    if "pure_arb" in result:
                        logger.info(f"  >> Pure arb executed! Profit: ${result['pure_arb']['expected_profit']:.2f}")
                    if "temporal_arb" in result:
                        logger.info(f"  >> Temporal arb executed! Direction: {result['temporal_arb']['direction']}")

                except Exception as e:
                    logger.error(f"Scan error: {e}")

                await asyncio.sleep(scan_interval)

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("\nBot stopped by user")
            self._show_market_summary()
            self.risk_manager.save_state()

        finally:
            self.price_feed.stop()
            logger.info("Bot shutdown complete")


def main():
    """Entry point."""
    settings = load_settings()

    # Ensure logs directory exists
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    bot = PolymarketArbBot(settings)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
