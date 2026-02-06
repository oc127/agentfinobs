"""
CEX (Centralized Exchange) real-time price feed for BTC.

Monitors Binance BTC/USDT price via WebSocket to detect momentum
that Polymarket 15-minute markets haven't yet priced in.

This is the core of the "temporal arbitrage" strategy:
- When BTC moves significantly on Binance but Polymarket still shows ~50/50,
  we can buy the correct side cheaply.
"""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    """A single BTC price observation."""
    price: float
    timestamp: float  # Unix timestamp
    source: str = "binance"


@dataclass
class MomentumSignal:
    """Represents a detected momentum signal."""
    direction: str           # "UP" or "DOWN"
    confidence: float        # 0.0 to 1.0
    price_change_pct: float  # Percentage change
    current_price: float
    reference_price: float   # Price at start of window
    window_seconds: int      # Lookback window used
    timestamp: float


class BinancePriceFeed:
    """Real-time BTC price feed from Binance via WebSocket and REST API."""

    STREAM_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"
    REST_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
    KLINE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, history_seconds: int = 1200):
        self._prices: deque[PriceSnapshot] = deque(maxlen=10000)
        self._current_price: Optional[float] = None
        self._last_update: float = 0.0
        self._history_seconds = history_seconds
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None

        # Track the price at the start of each 15-minute window
        self._window_start_price: Optional[float] = None
        self._window_start_time: float = 0.0

    @property
    def current_price(self) -> Optional[float]:
        return self._current_price

    @property
    def last_update(self) -> float:
        return self._last_update

    @property
    def price_count(self) -> int:
        return len(self._prices)

    def set_window_start(self, price: Optional[float] = None):
        """Mark the start of a new 15-minute window."""
        self._window_start_price = price or self._current_price
        self._window_start_time = time.time()
        logger.info(
            f"[CEX] Window start price set: ${self._window_start_price:,.2f}"
        )

    async def fetch_current_price(self) -> Optional[float]:
        """Fetch current BTC price via REST API (fallback)."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.REST_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    data = await resp.json()
                    price = float(data["price"])
                    self._record_price(price)
                    return price
        except Exception as e:
            logger.warning(f"[CEX] REST price fetch failed: {e}")
            return None

    def _record_price(self, price: float):
        """Record a new price observation."""
        now = time.time()
        self._current_price = price
        self._last_update = now
        self._prices.append(PriceSnapshot(price=price, timestamp=now))

        # Trim old entries
        cutoff = now - self._history_seconds
        while self._prices and self._prices[0].timestamp < cutoff:
            self._prices.popleft()

    async def start_websocket(self):
        """Start the Binance WebSocket price stream."""
        self._running = True
        logger.info("[CEX] Starting Binance BTC/USDT WebSocket feed...")

        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        self.STREAM_URL,
                        heartbeat=20,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as ws:
                        logger.info("[CEX] Connected to Binance WebSocket")
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    price = float(data.get("p", 0))
                                    if price > 0:
                                        self._record_price(price)
                                except (json.JSONDecodeError, ValueError, KeyError):
                                    continue
                            elif msg.type in (
                                aiohttp.WSMsgType.ERROR,
                                aiohttp.WSMsgType.CLOSED,
                            ):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[CEX] WebSocket error: {e}; reconnecting in 2s...")
                await asyncio.sleep(2)

    def stop(self):
        """Stop the WebSocket feed."""
        self._running = False
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()

    def get_momentum(self, lookback_seconds: int = 60) -> Optional[MomentumSignal]:
        """
        Analyze recent price action to detect momentum.

        This is the key function for temporal arbitrage:
        - Looks at price change over the last N seconds
        - Determines direction and confidence
        """
        if not self._prices or self._current_price is None:
            return None

        now = time.time()
        cutoff = now - lookback_seconds

        # Find the oldest price within the lookback window
        reference_price = None
        for snap in self._prices:
            if snap.timestamp >= cutoff:
                reference_price = snap.price
                break

        if reference_price is None or reference_price == 0:
            return None

        change_pct = ((self._current_price - reference_price) / reference_price) * 100

        # Determine direction and confidence based on magnitude of move
        abs_change = abs(change_pct)

        if abs_change < 0.01:
            return None  # No significant movement

        direction = "UP" if change_pct > 0 else "DOWN"

        # Confidence mapping: larger moves = higher confidence
        # These thresholds are calibrated for 15-minute BTC markets
        if abs_change >= 0.50:
            confidence = 0.95
        elif abs_change >= 0.30:
            confidence = 0.85
        elif abs_change >= 0.15:
            confidence = 0.75
        elif abs_change >= 0.08:
            confidence = 0.65
        elif abs_change >= 0.05:
            confidence = 0.55
        else:
            confidence = 0.45

        return MomentumSignal(
            direction=direction,
            confidence=confidence,
            price_change_pct=change_pct,
            current_price=self._current_price,
            reference_price=reference_price,
            window_seconds=lookback_seconds,
            timestamp=now,
        )

    def get_window_momentum(self) -> Optional[MomentumSignal]:
        """
        Get momentum relative to the start of the current 15-minute window.
        This is the most important signal for temporal arbitrage.
        """
        if (
            self._window_start_price is None
            or self._current_price is None
            or self._window_start_price == 0
        ):
            return None

        change_pct = (
            (self._current_price - self._window_start_price)
            / self._window_start_price
        ) * 100

        abs_change = abs(change_pct)
        if abs_change < 0.005:
            return None

        direction = "UP" if change_pct > 0 else "DOWN"

        # Window-based confidence (more reliable than short lookback)
        if abs_change >= 0.40:
            confidence = 0.95
        elif abs_change >= 0.25:
            confidence = 0.90
        elif abs_change >= 0.15:
            confidence = 0.80
        elif abs_change >= 0.10:
            confidence = 0.70
        elif abs_change >= 0.05:
            confidence = 0.60
        else:
            confidence = 0.50

        elapsed = time.time() - self._window_start_time

        return MomentumSignal(
            direction=direction,
            confidence=confidence,
            price_change_pct=change_pct,
            current_price=self._current_price,
            reference_price=self._window_start_price,
            window_seconds=int(elapsed),
            timestamp=time.time(),
        )

    def get_multi_timeframe_signal(self) -> Optional[MomentumSignal]:
        """
        Combine multiple timeframe signals for higher confidence.
        Uses 15s, 30s, 60s, and window-start lookbacks.
        """
        signals = []
        for lb in [15, 30, 60]:
            sig = self.get_momentum(lookback_seconds=lb)
            if sig:
                signals.append(sig)

        window_sig = self.get_window_momentum()
        if window_sig:
            signals.append(window_sig)

        if not signals:
            return None

        # All signals must agree on direction
        directions = set(s.direction for s in signals)
        if len(directions) > 1:
            return None  # Conflicting signals

        direction = directions.pop()

        # Combined confidence: weighted average with window signal having highest weight
        total_weight = 0.0
        weighted_conf = 0.0
        for i, sig in enumerate(signals):
            weight = 1.0 + (i * 0.5)  # Later (longer) timeframes get more weight
            if sig == window_sig:
                weight = 3.0  # Window signal is most important
            weighted_conf += sig.confidence * weight
            total_weight += weight

        combined_confidence = weighted_conf / total_weight if total_weight > 0 else 0.0

        # Use the window signal's price data if available, else the latest
        best = window_sig or signals[-1]

        return MomentumSignal(
            direction=direction,
            confidence=combined_confidence,
            price_change_pct=best.price_change_pct,
            current_price=best.current_price,
            reference_price=best.reference_price,
            window_seconds=best.window_seconds,
            timestamp=time.time(),
        )
