"""Domain models: trades, alerts, watchers, orders, positions."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Trade:
    """A single public trade from Polymarket's data API."""

    tx_hash: str
    market_title: str
    market_slug: str = ""
    condition_id: str = ""
    token_id: str = ""
    side: str = "BUY"          # BUY or SELL (taker side)
    outcome: str = "Yes"       # Yes or No
    size_shares: float = 0.0
    price: float = 0.0          # 0..1, also the implied probability
    timestamp: int = 0
    trader: str = ""

    @property
    def usd_value(self) -> float:
        return round(self.size_shares * self.price, 2)

    @property
    def prob_pct(self) -> float:
        return round(self.price * 100, 1)

    @classmethod
    def from_data_api(cls, raw: dict) -> "Trade":
        """Parse one entry of GET https://data-api.polymarket.com/trades."""
        try:
            size = float(raw.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        try:
            price = float(raw.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            ts = int(raw.get("timestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        return cls(
            tx_hash=str(raw.get("transactionHash") or ""),
            market_title=str(raw.get("title") or "Unknown market"),
            market_slug=str(raw.get("slug") or ""),
            condition_id=str(raw.get("conditionId") or ""),
            token_id=str(raw.get("asset") or ""),
            side=str(raw.get("side") or "BUY").upper(),
            outcome=str(raw.get("outcome") or "Yes"),
            size_shares=size,
            price=price,
            timestamp=ts,
            trader=str(raw.get("pseudonym") or raw.get("name") or ""),
        )

    def market_url(self) -> str:
        if self.market_slug:
            return f"https://polymarket.com/event/{self.market_slug}"
        return "https://polymarket.com"


@dataclass
class WatcherConfig:
    """One alert rule: what counts as a whale for this watcher."""

    name: str = "default"
    min_usd: float = 10000.0
    prob_min: float = 0.05
    prob_max: float = 0.95
    allow_slugs: list = field(default_factory=list)   # empty = all markets
    block_slugs: list = field(default_factory=list)
    enabled: bool = True

    def matches(self, trade: Trade) -> bool:
        if not self.enabled:
            return False
        if trade.usd_value < self.min_usd:
            return False
        if not (self.prob_min <= trade.price <= self.prob_max):
            return False
        slug = trade.market_slug
        if self.allow_slugs and slug not in self.allow_slugs:
            return False
        if slug and slug in self.block_slugs:
            return False
        return True


@dataclass
class WhaleAlert:
    """A trade that tripped a watcher."""

    trade: Trade
    watcher_name: str
    detected_at: int = 0

    def __post_init__(self) -> None:
        if not self.detected_at:
            self.detected_at = int(time.time())

    def headline(self) -> str:
        t = self.trade
        return (
            f"🐋 Whale {t.side} {t.outcome} "
            f"${t.usd_value:,.0f} @ {t.prob_pct}% — {t.market_title}"
        )

    def format_telegram(self) -> str:
        t = self.trade
        return (
            f"🐋 <b>WHALE {t.side}</b> {t.outcome}\n"
            f"<b>${t.usd_value:,.0f}</b> @ {t.prob_pct}%\n"
            f"{t.market_title}\n"
            f"👤 {t.trader or 'anon'}\n"
            f'🔗 <a href="{t.market_url()}">Open market</a>'
        )


@dataclass
class OrderPreview:
    """Dry-run preview of a live order. Creating one signs NOTHING."""

    token_id: str
    market_title: str
    side: str            # "BUY" or "SELL"
    outcome: str         # "Yes" or "No"
    price: float         # limit price 0..1
    size_shares: float
    usd_value: float
    mode: str = "live"

    def summary(self) -> str:
        return (
            f"REAL order preview — {self.side} {self.outcome} "
            f"${self.usd_value:,.2f} ({self.size_shares:,.2f} shares @ {self.price:.3f}) "
            f"on '{self.market_title}'"
        )


@dataclass
class PaperPosition:
    """A simulated follow of a whale alert. No real money."""

    id: int = 0
    market_title: str = ""
    market_slug: str = ""
    token_id: str = ""
    side: str = "BUY"
    outcome: str = "Yes"
    entry_price: float = 0.0
    size_usd: float = 0.0
    opened_at: int = 0
    closed_at: int = 0
    exit_price: float = 0.0
    status: str = "open"   # open | closed

    def pnl_usd(self, current_price: float) -> float:
        """P&L in USD at a given current price."""
        if self.entry_price <= 0:
            return 0.0
        shares = self.size_usd / self.entry_price
        if self.side == "BUY":
            return round((current_price - self.entry_price) * shares, 2)
        return round((self.entry_price - current_price) * shares, 2)
