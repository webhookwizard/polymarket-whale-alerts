import pytest

from src.models import OrderPreview, PaperPosition, Trade, WatcherConfig, WhaleAlert
from tests.conftest import make_trade


def test_trade_usd_value():
    t = make_trade(usd=20_000, price=0.5)
    assert t.usd_value == 20_000


def test_trade_from_data_api():
    raw = {"transactionHash": "0xhash", "title": "Q?", "slug": "q",
           "conditionId": "0xcond", "asset": "tok9", "side": "SELL",
           "outcome": "No", "size": "100", "price": "0.4",
           "timestamp": "1700000000", "pseudonym": "whale1"}
    t = Trade.from_data_api(raw)
    assert t.tx_hash == "0xhash"
    assert t.side == "SELL"
    assert t.usd_value == 40.0
    assert t.prob_pct == 40.0


def test_trade_from_data_api_bad_numbers():
    t = Trade.from_data_api({"size": "nan!", "price": None})
    assert t.size_shares == 0.0
    assert t.price == 0.0


def test_watcher_matches_threshold():
    w = WatcherConfig(min_usd=10_000)
    assert w.matches(make_trade(usd=15_000))
    assert not w.matches(make_trade(usd=9_999))


def test_watcher_prob_filter():
    w = WatcherConfig(prob_min=0.1, prob_max=0.9)
    assert w.matches(make_trade(price=0.5))
    assert not w.matches(make_trade(price=0.05))
    assert not w.matches(make_trade(price=0.95))


def test_watcher_allow_block_lists():
    w = WatcherConfig(allow_slugs=["a"])
    assert w.matches(make_trade(slug="a"))
    assert not w.matches(make_trade(slug="b"))
    w2 = WatcherConfig(block_slugs=["a"])
    assert not w2.matches(make_trade(slug="a"))
    assert w2.matches(make_trade(slug="b"))


def test_watcher_disabled():
    w = WatcherConfig(enabled=False)
    assert not w.matches(make_trade())


def test_alert_headline_and_telegram_format():
    a = WhaleAlert(trade=make_trade(usd=25_000, price=0.5), watcher_name="w")
    h = a.headline()
    assert "25,000" in h and "Whale" in h
    tg = a.format_telegram()
    assert "polymarket.com" in tg
    assert "<b>" in tg


def test_order_preview_summary_has_no_secrets():
    p = OrderPreview(token_id="t", market_title="M", side="BUY",
                     outcome="Yes", price=0.5, size_shares=50, usd_value=25)
    s = p.summary()
    assert "REAL order preview" in s
    assert "$25.00" in s


def test_paper_pnl_buy():
    p = PaperPosition(entry_price=0.5, size_usd=25, side="BUY")
    assert p.pnl_usd(0.6) == 5.0
    assert p.pnl_usd(0.4) == -5.0


def test_paper_pnl_sell():
    p = PaperPosition(entry_price=0.5, size_usd=25, side="SELL")
    assert p.pnl_usd(0.4) == 5.0
    assert p.pnl_usd(0.6) == -5.0
