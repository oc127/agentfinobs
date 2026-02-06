"""
Trading execution module for Polymarket CLOB API.

Handles order creation, submission, monitoring, and position management.
"""

# SSL patch
from . import ssl_patch  # noqa: F401

import logging
import time
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    BalanceAllowanceParams,
    AssetType,
    OrderArgs,
    OrderType,
    PostOrdersArgs,
    PartialCreateOrderOptions,
)
from py_clob_client.order_builder.constants import BUY, SELL

from .config import Settings

logger = logging.getLogger(__name__)

_cached_client: Optional[ClobClient] = None


def get_client(settings: Settings) -> ClobClient:
    """Get or create a ClobClient instance."""
    global _cached_client

    if _cached_client is not None:
        return _cached_client

    if not settings.private_key:
        raise RuntimeError("POLYMARKET_PRIVATE_KEY is required")

    host = "https://clob.polymarket.com"

    _cached_client = ClobClient(
        host,
        key=settings.private_key.strip(),
        chain_id=137,
        signature_type=settings.signature_type,
        funder=settings.funder.strip() if settings.funder else None,
    )

    # Always use derived credentials (most reliable with GNOSIS_SAFE)
    logger.info("Deriving API credentials from private key...")
    derived_creds = _cached_client.create_or_derive_api_creds()
    _cached_client.set_api_creds(derived_creds)
    logger.info(f"  API Key: {derived_creds.api_key}")

    logger.info(f"  Wallet: {_cached_client.get_address()}")
    logger.info(f"  Signature Type: {settings.signature_type} ({'GNOSIS_SAFE' if settings.signature_type == 2 else 'EOA'})")
    logger.info(f"  Funder/Proxy: {settings.funder or 'N/A'}")

    return _cached_client


def get_balance(settings: Settings) -> float:
    """Get USDC balance from Polymarket account."""
    try:
        client = get_client(settings)
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=settings.signature_type,
        )
        result = client.get_balance_allowance(params)

        if isinstance(result, dict):
            balance_raw = result.get("balance", "0")
            balance_wei = float(balance_raw)
            return balance_wei / 1_000_000  # USDC has 6 decimals
        return 0.0
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return 0.0


def get_order_book(client: ClobClient, token_id: str) -> dict:
    """Get order book for a token, returning normalized dict."""
    try:
        book = client.get_order_book(token_id=token_id)
        bids_raw = book.bids if hasattr(book, "bids") and book.bids else []
        asks_raw = book.asks if hasattr(book, "asks") and book.asks else []

        def to_tuples(levels):
            result = []
            for level in levels:
                try:
                    price = float(level.price)
                    size = float(level.size)
                except Exception:
                    continue
                if size > 0:
                    result.append((price, size))
            return result

        bid_levels = to_tuples(bids_raw)
        ask_levels = to_tuples(asks_raw)

        best_bid = max((p for p, _ in bid_levels), default=None)
        best_ask = min((p for p, _ in ask_levels), default=None)

        bid_size = next((s for p, s in bid_levels if p == best_bid), 0.0) if best_bid else 0.0
        ask_size = next((s for p, s in ask_levels if p == best_ask), 0.0) if best_ask else 0.0

        spread = (best_ask - best_bid) if (best_bid and best_ask) else None

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "bid_size": bid_size,
            "ask_size": ask_size,
            "bids": bid_levels,
            "asks": ask_levels,
        }
    except Exception as e:
        logger.error(f"Error getting order book: {e}")
        return {}


def compute_buy_fill(
    asks: list[tuple[float, float]], target_size: float
) -> Optional[dict]:
    """
    Compute fill information for buying target_size shares using the ask book.

    Returns dict with: filled, vwap, worst, best, cost
    """
    if target_size <= 0 or not asks:
        return None

    sorted_asks = sorted(asks, key=lambda x: x[0])
    filled = 0.0
    cost = 0.0
    worst = None
    best = sorted_asks[0][0]

    for price, size in sorted_asks:
        if filled >= target_size:
            break
        take = min(size, target_size - filled)
        cost += take * price
        filled += take
        worst = price

    if filled + 1e-9 < target_size:
        return None

    vwap = cost / filled if filled > 0 else None
    return {
        "filled": filled,
        "vwap": vwap,
        "worst": worst,
        "best": best,
        "cost": cost,
    }


def place_order(
    settings: Settings,
    *,
    side: str,
    token_id: str,
    price: float,
    size: float,
    tif: str = "GTC",
) -> dict:
    """Place a single order."""
    client = get_client(settings)

    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size,
        side=BUY if side.upper() == "BUY" else SELL,
    )

    options = PartialCreateOrderOptions(neg_risk=True)
    signed_order = client.create_order(order_args, options)

    tif_up = (tif or "GTC").upper()
    order_type = getattr(OrderType, tif_up, OrderType.GTC)
    return client.post_order(signed_order, order_type)


def place_orders_fast(
    settings: Settings, orders: list[dict], *, order_type: str = "FOK"
) -> list[dict]:
    """
    Place multiple orders as fast as possible.
    Pre-signs all orders, then submits together.
    """
    client = get_client(settings)

    tif_up = (order_type or "GTC").upper()
    ot = getattr(OrderType, tif_up, OrderType.GTC)

    options = PartialCreateOrderOptions(neg_risk=True)
    signed_orders = []

    for order_params in orders:
        order_args = OrderArgs(
            token_id=order_params["token_id"],
            price=order_params["price"],
            size=order_params["size"],
            side=BUY if order_params["side"].upper() == "BUY" else SELL,
        )
        signed_order = client.create_order(order_args, options)
        signed_orders.append(signed_order)

    # Try batch submission first
    try:
        args = [PostOrdersArgs(order=o, orderType=ot) for o in signed_orders]
        result = client.post_orders(args)
        return result if isinstance(result, list) else [result]
    except Exception:
        # Fallback to sequential
        results = []
        for signed_order in signed_orders:
            try:
                results.append(client.post_order(signed_order, ot))
            except Exception as exc:
                results.append({"error": str(exc)})
        return results


def extract_order_id(result: dict) -> Optional[str]:
    """Extract order ID from API response."""
    if not isinstance(result, dict):
        return None
    for key in ("orderID", "orderId", "order_id", "id"):
        val = result.get(key)
        if val:
            return str(val)
    for key in ("order", "data", "result"):
        nested = result.get(key)
        if isinstance(nested, dict):
            oid = extract_order_id(nested)
            if oid:
                return oid
    return None


def wait_for_terminal_order(
    settings: Settings,
    order_id: str,
    *,
    requested_size: Optional[float] = None,
    timeout_seconds: float = 3.0,
    poll_interval_seconds: float = 0.25,
) -> dict:
    """Poll order state until terminal or timeout."""
    terminal_statuses = {"filled", "canceled", "cancelled", "rejected", "expired"}
    client = get_client(settings)
    start = time.monotonic()
    last_summary = None

    while (time.monotonic() - start) < timeout_seconds:
        try:
            od = client.get_order(order_id)
            status = str(od.get("status", "") or od.get("state", "")).lower()
            filled_size = None
            for key in ("filled_size", "filledSize", "size_filled", "matched_size"):
                if key in od:
                    try:
                        filled_size = float(od[key])
                    except (ValueError, TypeError):
                        pass
                    break

            last_summary = {
                "status": status,
                "filled_size": filled_size,
                "requested_size": requested_size,
                "raw": od,
            }

            if requested_size and filled_size and filled_size + 1e-9 >= requested_size:
                last_summary["filled"] = True
                return last_summary

            if status in terminal_statuses:
                last_summary["filled"] = status == "filled"
                return last_summary

        except Exception as exc:
            last_summary = {
                "status": "error",
                "error": str(exc),
                "filled_size": None,
                "requested_size": requested_size,
            }

        time.sleep(poll_interval_seconds)

    if last_summary is None:
        last_summary = {"status": None, "filled_size": None, "requested_size": requested_size}
    last_summary.setdefault("filled", False)
    return last_summary


def cancel_orders(settings: Settings, order_ids: list[str]) -> Optional[dict]:
    """Cancel one or more orders."""
    if not order_ids:
        return None
    client = get_client(settings)
    return client.cancel_orders(order_ids)


def get_positions(settings: Settings, token_ids: list[str] = None) -> dict:
    """Get current positions for the user."""
    try:
        client = get_client(settings)
        positions = client.get_positions()
        result = {}
        for pos in positions:
            token_id = pos.get("asset", {}).get("token_id") or pos.get("token_id")
            if token_id:
                if token_ids is None or token_id in token_ids:
                    result[token_id] = {
                        "size": float(pos.get("size", 0)),
                        "avg_price": float(pos.get("avg_price", 0)),
                        "raw": pos,
                    }
        return result
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        return {}
