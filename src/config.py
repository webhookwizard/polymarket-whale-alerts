"""Configuration, loaded from environment variables.

Paper mode is the default. Live trading requires BOTH
POLY_LIVE_TRADING=true AND POLY_PRIVATE_KEY — see live_trader.py.
"""
from __future__ import annotations

import os
import re


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes")


_PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def looks_like_private_key(value: str) -> bool:
    """Heuristic check: 0x + 64 hex chars. Never logs the value itself."""
    return bool(_PRIVATE_KEY_RE.match((value or "").strip()))


class Config:
    """All runtime settings. Construct via Config.from_env()."""

    def __init__(self) -> None:
        # Watcher
        self.poll_interval_sec: float = _get_float("POLL_INTERVAL_SEC", 15.0)
        self.default_min_usd: float = _get_float("DEFAULT_MIN_USD", 10000.0)
        self.default_prob_min: float = _get_float("DEFAULT_PROB_MIN", 0.05)
        self.default_prob_max: float = _get_float("DEFAULT_PROB_MAX", 0.95)
        # Telegram
        self.tg_token: str = os.environ.get("TG_BOT_TOKEN", "").strip()
        self.tg_default_chat: str = os.environ.get("TG_DEFAULT_CHAT_ID", "").strip()
        # Web dashboard
        self.web_host: str = os.environ.get("WEB_HOST", "127.0.0.1")
        self.web_port: int = int(os.environ.get("WEB_PORT", "5000") or 5000)
        self.db_path: str = os.environ.get("DB_PATH", "whale_alerts.db")
        # Live trading (real money) — OFF unless explicitly enabled
        self.live_trading: bool = _get_bool("POLY_LIVE_TRADING", False)
        self.private_key: str = os.environ.get("POLY_PRIVATE_KEY", "").strip()
        self.max_order_usd: float = _get_float("POLY_MAX_ORDER_USD", 25.0)
        self.chain_id: int = int(os.environ.get("POLY_CHAIN_ID", "137") or 137)
        self.wallet_override: str = os.environ.get("POLY_WALLET", "").strip()

    @classmethod
    def from_env(cls) -> "Config":
        return cls()

    # -- live-trading gate -------------------------------------------------
    def live_gate(self) -> tuple[bool, str]:
        """Return (allowed, reason). Both flag AND key must be present and sane.

        The reason string never contains the key.
        """
        if not self.live_trading:
            return False, "POLY_LIVE_TRADING is not 'true' — staying in paper mode"
        if not self.private_key:
            return False, "POLY_PRIVATE_KEY is not set — staying in paper mode"
        if not looks_like_private_key(self.private_key):
            return (
                False,
                "POLY_PRIVATE_KEY is set but malformed "
                "(expected 0x + 64 hex chars) — staying in paper mode",
            )
        return True, "live mode enabled"

    @property
    def live_enabled(self) -> bool:
        ok, _ = self.live_gate()
        return ok

    def key_fingerprint(self) -> str:
        """Non-sensitive identifier for logs: first/last 4 chars only."""
        k = self.private_key.strip()
        if not k:
            return "<no-key>"
        return f"{k[:6]}…{k[-4:]}"
