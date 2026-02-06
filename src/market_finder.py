"""
Market finder module for Polymarket BTC 15-minute markets.

Automatically discovers the current active market and handles
transitions between 15-minute windows.
"""

# SSL patch
from . import ssl_patch  # noqa: F401

import json
import logging
import re
import time
from typing import Optional, Dict

import requests

logger = logging.getLogger(__name__)

BTC_15M_WINDOW = 900  # 15 minutes in seconds

GAMMA_API = "https://gamma-api.polymarket.com"


def _gamma_get(path: str, params: dict = None) -> Optional[dict | list]:
    """Make a GET request to Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_API}{path}",
            params=params or {},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug("Gamma API request failed: %s", e)
        return None


def fetch_market_from_slug(slug: str) -> Dict[str, str]:
    """Fetch market details from a Polymarket event slug via Gamma API."""
    slug = slug.split("?")[0]

    events = _gamma_get("/events", {"slug": slug})
    if not events or not isinstance(events, list) or len(events) == 0:
        raise RuntimeError(f"Could not fetch market data for slug '{slug}'")

    event = events[0]
    markets = event.get("markets", [])
    if not markets:
        raise RuntimeError(f"No markets found for slug '{slug}'")

    market = markets[0]
    clob_tokens_raw = market.get("clobTokenIds", "[]")
    if isinstance(clob_tokens_raw, str):
        clob_tokens = json.loads(clob_tokens_raw)
    else:
        clob_tokens = clob_tokens_raw

    outcomes_raw = market.get("outcomes", "[]")
    if isinstance(outcomes_raw, str):
        outcomes = json.loads(outcomes_raw)
    else:
        outcomes = outcomes_raw

    if len(clob_tokens) != 2 or len(outcomes) != 2:
        raise RuntimeError("Expected binary market with two clob tokens")

    return {
        "market_id": market.get("id", ""),
        "yes_token_id": clob_tokens[0],
        "no_token_id": clob_tokens[1],
        "outcomes": outcomes,
        "question": market.get("question", ""),
        "slug": slug,
        "start_date": market.get("startDate"),
        "end_date": market.get("endDate"),
    }


def _find_via_computed_slugs() -> Optional[str]:
    """Try computed slugs for current and next 15m windows."""
    now_ts = int(time.time())
    for i in range(5):
        ts = now_ts + (i * BTC_15M_WINDOW)
        ts_rounded = (ts // BTC_15M_WINDOW) * BTC_15M_WINDOW
        slug = f"btc-updown-15m-{ts_rounded}"
        try:
            fetch_market_from_slug(slug)
            if now_ts < ts_rounded + BTC_15M_WINDOW:
                return slug
        except Exception:
            continue
    return None


def _find_via_gamma_api() -> Optional[str]:
    """Find BTC 15m slug from Polymarket Gamma API."""
    try:
        data = _gamma_get("/events", {"tag": "15M", "closed": "false", "limit": "10"})
        if not data or not isinstance(data, list):
            return None

        now_ts = int(time.time())
        pattern = re.compile(r"^btc-updown-15m-(\d+)$")
        candidates = []

        for event in data:
            slug = (event.get("slug") or "").strip()
            mo = pattern.match(slug)
            if not mo:
                continue
            ts = int(mo.group(1))
            if now_ts < ts + BTC_15M_WINDOW:
                candidates.append((ts, slug))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None
    except Exception as e:
        logger.debug("Gamma API search failed: %s", e)
        return None


def get_active_btc_15m_slug() -> str:
    """
    Find the current active BTC 15min market on Polymarket.

    Tries multiple methods:
    1. Computed slugs (fastest)
    2. Gamma API tag search (reliable)
    """
    logger.info("Searching for current BTC 15min market...")

    slug = _find_via_computed_slugs()
    if slug:
        logger.info("Market found (computed slug): %s", slug)
        return slug

    slug = _find_via_gamma_api()
    if slug:
        logger.info("Market found (Gamma API): %s", slug)
        return slug

    raise RuntimeError(
        "No active BTC 15min market found. "
        "Set POLYMARKET_MARKET_SLUG in .env to override."
    )


def get_market_timestamps(slug: str) -> tuple[Optional[int], Optional[int]]:
    """Extract start and end timestamps from a market slug."""
    match = re.search(r"btc-updown-15m-(\d+)", slug)
    if not match:
        return None, None
    start_ts = int(match.group(1))
    end_ts = start_ts + BTC_15M_WINDOW
    return start_ts, end_ts


def get_time_remaining(slug: str) -> str:
    """Get human-readable time remaining for a market."""
    _, end_ts = get_market_timestamps(slug)
    if end_ts is None:
        return "Unknown"

    remaining = end_ts - int(time.time())
    if remaining <= 0:
        return "CLOSED"

    minutes = remaining // 60
    seconds = remaining % 60
    return f"{minutes}m {seconds}s"
