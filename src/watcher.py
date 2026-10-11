"""Whale watcher: polls the public trade tape, emits WhaleAlerts.

Works with any feed object exposing `get_trades(limit) -> list[Trade]`
(the real PolymarketClient) or `batch(n)` (MockFeed, adapted below).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .models import Trade, WatcherConfig, WhaleAlert

log = logging.getLogger(__name__)

# Cap on remembered tx hashes so long-running watchers don't grow forever.
_MAX_SEEN = 50_000


class WhaleWatcher:
    def __init__(
        self,
        feed,
        watchers: list[WatcherConfig] | None = None,
        on_alert: Callable[[WhaleAlert], None] | None = None,
    ) -> None:
        self.feed = feed
        self.watchers = watchers or [WatcherConfig()]
        self.on_alert = on_alert
        self._seen: set[str] = set()
        self.running = False
        self.polls = 0
        self.alerts_emitted = 0

    # -- feed adapter ---------------------------------------------------
    def _fetch(self, limit: int = 60) -> list[Trade]:
        if hasattr(self.feed, "get_trades"):
            return self.feed.get_trades(limit=limit)
        if hasattr(self.feed, "batch"):  # MockFeed
            return self.feed.batch(limit)
        raise TypeError("feed must expose get_trades() or batch()")

    def _remember(self, tx_hash: str) -> bool:
        """True if this tx was already seen (dedupe)."""
        if not tx_hash:
            return True
        if tx_hash in self._seen:
            return True
        self._seen.add(tx_hash)
        if len(self._seen) > _MAX_SEEN:
            # Drop the oldest ~10%: sets are unordered, so just trim.
            self._seen = set(list(self._seen)[-_MAX_SEEN // 2:])
        return False

    # -- core -----------------------------------------------------------
    def poll_once(self, limit: int = 60) -> list[WhaleAlert]:
        """One poll cycle. Returns the alerts it produced."""
        alerts: list[WhaleAlert] = []
        try:
            trades = self._fetch(limit)
        except Exception as exc:
            log.warning("Poll failed: %s", exc)
            return alerts
        self.polls += 1
        for trade in trades:
            if self._remember(trade.tx_hash):
                continue
            for watcher in self.watchers:
                if watcher.matches(trade):
                    alert = WhaleAlert(trade=trade, watcher_name=watcher.name)
                    alerts.append(alert)
                    self.alerts_emitted += 1
                    if self.on_alert:
                        try:
                            self.on_alert(alert)
                        except Exception as exc:
                            log.warning("on_alert handler failed: %s", exc)
                    break  # one alert per trade (first matching watcher)
        return alerts

    def run(self, interval_sec: float = 15.0, max_polls: int | None = None) -> None:
        """Blocking poll loop. Ctrl-C to stop."""
        self.running = True
        polls_done = 0
        log.info("Watcher started (%d rule(s))", len(self.watchers))
        try:
            while self.running:
                self.poll_once()
                polls_done += 1
                if max_polls is not None and polls_done >= max_polls:
                    break
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            log.info("Watcher stopped after %d polls, %d alerts",
                     polls_done, self.alerts_emitted)

    def stop(self) -> None:
        self.running = False
