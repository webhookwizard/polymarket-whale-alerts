"""Paper trading: simulated follows of whale alerts. No real money, ever."""
from __future__ import annotations

import logging
import time

from .models import PaperPosition, WhaleAlert
from .storage import Storage

log = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, storage: Storage, price_fn=None) -> None:
        """price_fn(token_id) -> current Yes price (0..1) or None."""
        self.storage = storage
        self.price_fn = price_fn

    def open_position(self, alert: WhaleAlert, size_usd: float) -> PaperPosition:
        t = alert.trade
        pos = PaperPosition(
            market_title=t.market_title,
            market_slug=t.market_slug,
            token_id=t.token_id,
            side=t.side,
            outcome=t.outcome,
            entry_price=t.price,
            size_usd=size_usd,
            opened_at=int(time.time()),
        )
        pos.id = self.storage.open_paper_position(pos)
        log.info("PAPER follow: %s %s $%.2f @ %.3f (pos #%d)",
                 t.side, t.outcome, size_usd, t.price, pos.id)
        return pos

    def close_position(self, pos_id: int, exit_price: float | None = None) -> bool:
        pos = self.storage.get_position(pos_id)
        if not pos or pos.status != "open":
            return False
        if exit_price is None:
            exit_price = self.current_price(pos.token_id) or pos.entry_price
        return self.storage.close_paper_position(pos_id, exit_price)

    def current_price(self, token_id: str) -> float | None:
        if not self.price_fn or not token_id:
            return None
        try:
            return self.price_fn(token_id)
        except Exception as exc:
            log.warning("price lookup failed: %s", exc)
            return None

    def pnl(self, pos: PaperPosition) -> float | None:
        cur = self.current_price(pos.token_id)
        if cur is None:
            return None
        return pos.pnl_usd(cur)

    def summary(self) -> dict:
        open_pos = self.storage.list_positions("open")
        closed_pos = self.storage.list_positions("closed")
        realized = sum(
            p.pnl_usd(p.exit_price) for p in closed_pos if p.exit_price > 0
        )
        return {
            "open": len(open_pos),
            "closed": len(closed_pos),
            "realized_pnl_usd": round(realized, 2),
        }
