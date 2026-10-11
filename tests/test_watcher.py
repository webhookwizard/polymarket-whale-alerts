from unittest.mock import MagicMock

from src.mock_feed import MockFeed
from src.models import WatcherConfig
from src.watcher import WhaleWatcher
from tests.conftest import make_trade


class ListFeed:
    def __init__(self, trades):
        self.trades = trades

    def get_trades(self, limit=60):
        return self.trades[:limit]


def test_detects_whale():
    w = WhaleWatcher(ListFeed([make_trade(usd=50_000)]),
                     [WatcherConfig(min_usd=10_000)])
    alerts = w.poll_once()
    assert len(alerts) == 1
    assert alerts[0].trade.usd_value == 50_000


def test_ignores_small_trades():
    w = WhaleWatcher(ListFeed([make_trade(usd=100)]),
                     [WatcherConfig(min_usd=10_000)])
    assert w.poll_once() == []


def test_dedupes_by_tx_hash():
    trades = [make_trade(usd=50_000, tx="0xsame")]
    w = WhaleWatcher(ListFeed(trades), [WatcherConfig(min_usd=10_000)])
    assert len(w.poll_once()) == 1
    assert w.poll_once() == []  # second poll: already seen


def test_on_alert_called():
    seen = []
    w = WhaleWatcher(ListFeed([make_trade(usd=50_000)]),
                     [WatcherConfig(min_usd=10_000)],
                     on_alert=seen.append)
    w.poll_once()
    assert len(seen) == 1


def test_on_alert_exception_does_not_kill_poll():
    def bad(alert):
        raise RuntimeError("boom")
    w = WhaleWatcher(ListFeed([make_trade(usd=50_000), make_trade(usd=60_000, tx="0x2")]),
                     [WatcherConfig(min_usd=10_000)], on_alert=bad)
    alerts = w.poll_once()
    assert len(alerts) == 2


def test_feed_failure_returns_empty():
    feed = MagicMock()
    feed.get_trades.side_effect = RuntimeError("network down")
    w = WhaleWatcher(feed, [WatcherConfig()])
    assert w.poll_once() == []


def test_mock_feed_adapter():
    w = WhaleWatcher(MockFeed(seed=9, whale_probability=1.0),
                     [WatcherConfig(min_usd=10_000)])
    alerts = w.poll_once(limit=10)
    assert len(alerts) == 10


def test_run_respects_max_polls():
    w = WhaleWatcher(ListFeed([]), [WatcherConfig()])
    w.run(interval_sec=0, max_polls=3)
    assert w.polls == 3
    assert not w.running
