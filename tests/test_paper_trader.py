from src.models import WhaleAlert
from tests.conftest import make_trade


def _alert():
    return WhaleAlert(trade=make_trade(usd=50_000, price=0.5), watcher_name="w")


def test_open_position(paper):
    pos = paper.open_position(_alert(), 25.0)
    assert pos.id > 0
    assert pos.entry_price == 0.5
    assert pos.size_usd == 25.0


def test_pnl_uses_price_fn(paper):
    pos = paper.open_position(_alert(), 25.0)  # entry 0.5, price_fn -> 0.70
    assert paper.pnl(pos) == 10.0  # (0.7-0.5) * 50 shares


def test_close_position(paper):
    pos = paper.open_position(_alert(), 25.0)
    assert paper.close_position(pos.id, 0.6)
    assert not paper.close_position(9999, 0.6)


def test_summary(paper):
    paper.open_position(_alert(), 25.0)
    s = paper.summary()
    assert s["open"] == 1 and s["closed"] == 0
