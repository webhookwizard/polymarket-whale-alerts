"""Routes a 'follow' to paper or live execution.

- Paper is the default everywhere.
- Live requires: global gate open (POLY_LIVE_TRADING=true + key) AND the
  chat opted in via /live on AND explicit confirmation for the order.
- Confirmation model: follow() with auto_confirm=False returns a
  PendingLiveOrder (dry-run preview, NOTHING signed). confirm_pending()
  executes it (cap re-checked). Session-level auto-confirm comes from
  --confirm-live (CLI) or the dashboard toggle.
"""
from __future__ import annotations

import logging
import time
import uuid

from .live_trader import LiveTrader, LiveTradingDisabled, NeedsConfirmation
from .models import OrderPreview, PaperPosition, WhaleAlert
from .paper_trader import PaperTrader
from .storage import Storage

log = logging.getLogger(__name__)


class PaperFollow:
    kind = "paper"

    def __init__(self, position: PaperPosition) -> None:
        self.position = position


class PendingLiveOrder:
    kind = "pending_live"

    def __init__(self, pending_id: str, preview: OrderPreview,
                 chat_id: str | None) -> None:
        self.pending_id = pending_id
        self.preview = preview
        self.chat_id = chat_id
        self.created_at = int(time.time())


class LiveFollow:
    kind = "live"

    def __init__(self, preview: OrderPreview, order_response) -> None:
        self.preview = preview
        self.order_response = order_response


class TradeRouter:
    def __init__(self, storage: Storage, paper: PaperTrader,
                 live: LiveTrader) -> None:
        self.storage = storage
        self.paper = paper
        self.live = live
        self.session_confirmed = False
        self._pending: dict[str, PendingLiveOrder] = {}

    # -- session confirmation (CLI --confirm-live / dashboard toggle) ------
    def confirm_session(self) -> None:
        self.session_confirmed = True
        log.info("Live session confirmed for this process run.")

    def chat_live(self, chat_id: str | None) -> bool:
        if chat_id is None:
            return False
        return self.storage.chat_live_enabled(chat_id)

    # -- follow ------------------------------------------------------------
    def follow(self, alert: WhaleAlert, size_usd: float,
               chat_id: str | None = None,
               auto_confirm: bool | None = None):
        """Follow a whale alert. Returns PaperFollow | PendingLiveOrder | LiveFollow."""
        t = alert.trade
        wants_live = self.chat_live(chat_id) and self.live.enabled
        if not wants_live:
            if chat_id and self.storage.chat_live_enabled(chat_id) \
                    and not self.live.enabled:
                ok, reason = self.live.config.live_gate()
                log.info("Chat wants live but gate closed (%s) — paper instead", reason)
            position = self.paper.open_position(alert, size_usd)
            return PaperFollow(position)

        preview = self.live.preview_order(
            token_id=t.token_id,
            market_title=t.market_title,
            side=t.side,
            outcome=t.outcome,
            price=t.price,
            size_usd=size_usd,
        )
        confirmed = self.session_confirmed if auto_confirm is None else auto_confirm
        if confirmed:
            return self._execute_live(preview)
        pending_id = uuid.uuid4().hex[:12]
        pending = PendingLiveOrder(pending_id, preview, chat_id)
        self._pending[pending_id] = pending
        log.info("Pending live order %s awaiting confirmation: %s",
                 pending_id, preview.summary())
        return pending

    def _execute_live(self, preview: OrderPreview) -> LiveFollow:
        try:
            resp = self.live.place_order(preview, confirmed=True)
        except NeedsConfirmation:
            # Should not happen (we pass confirmed=True) — defensive.
            raise LiveTradingDisabled("confirmation state mismatch")
        return LiveFollow(preview, resp)

    def confirm_pending(self, pending_id: str):
        pending = self._pending.pop(pending_id, None)
        if pending is None:
            raise KeyError(f"unknown pending order {pending_id}")
        return self._execute_live(pending.preview)

    def cancel_pending(self, pending_id: str) -> bool:
        return self._pending.pop(pending_id, None) is not None

    def pending_count(self) -> int:
        return len(self._pending)
