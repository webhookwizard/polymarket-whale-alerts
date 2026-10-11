"""Read-only client for Polymarket's PUBLIC APIs (no auth, no keys).

- Gamma API  (https://gamma-api.polymarket.com): market/event discovery.
- Data API   (https://data-api.polymarket.com): public trade tape.

All requests have timeouts and retries with backoff. Anything that needs
a wallet or signing lives in live_trader.py, never here.
"""
from __future__ import annotations

import logging
import time

import requests

from .models import Trade

log = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"


class PolymarketError(Exception):
    """Raised when the public APIs fail after retries."""


class PolymarketClient:
    def __init__(
        self,
        timeout: float = 10.0,
        max_retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "polymarket-whale-alerts/0.1"})

    # -- internals ------------------------------------------------------
    def _get(self, url: str, params: dict | None = None):
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                last_err = exc
                log.warning("GET %s failed (attempt %d/%d): %s",
                            url, attempt + 1, self.max_retries, exc)
                time.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
        raise PolymarketError(f"GET {url} failed after {self.max_retries} tries: {last_err}")

    # -- public API ------------------------------------------------------
    def get_trades(self, limit: int = 50) -> list[Trade]:
        """Latest public trades across all markets (newest first)."""
        raw = self._get(f"{DATA_BASE}/trades", {"limit": max(1, min(limit, 200))})
        trades = []
        for item in raw or []:
            try:
                trades.append(Trade.from_data_api(item))
            except Exception as exc:  # one bad row must not kill the poll
                log.warning("Skipping malformed trade row: %s", exc)
        return trades

    def get_event(self, slug: str) -> dict:
        """Full event payload (markets, prices) from the Gamma API."""
        return self._get(f"{GAMMA_BASE}/events/slug/{slug}")

    def search_markets(self, query: str, limit: int = 10) -> list[dict]:
        """Search markets by keyword via the Gamma API."""
        data = self._get(f"{GAMMA_BASE}/public-search", {"q": query})
        if isinstance(data, dict):
            return data.get("events", [])[:limit]
        return list(data or [])[:limit]

    def get_market_price(self, token_id: str) -> float | None:
        """Current Yes price for a token via the CLOB midpoint (public)."""
        try:
            data = self._get(
                "https://clob.polymarket.com/midpoint", {"token_id": token_id}
            )
            return float(data.get("mid", 0) or 0) or None
        except (PolymarketError, TypeError, ValueError):
            return None
