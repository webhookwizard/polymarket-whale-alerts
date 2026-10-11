import pytest

from src.live_trader import LiveTrader
from src.models import WhaleAlert
from src.trade_router import (LiveFollow, PaperFollow, PendingLiveOrder,
                              TradeRouter)
from tests.conftest import FAKE_KEY, FakeSdk, make_config, make_trade


def _alert():
    return WhaleAlert(trade=make_trade(usd=50_000, price=0.5), watcher_name="w")


def _live_router(storage, paper, live_on=True):
    cfg = make_config(live_trading=live_on, private_key=FAKE_KEY,
                      max_order_usd=1000)
    live = LiveTrader(cfg, sdk=FakeSdk)
    return TradeRouter(storage, paper, live)


def test_follow_defaults_to_paper(router):
    r = router.follow(_alert(), 25.0, chat_id="999")
    assert isinstance(r, PaperFollow)


def test_live_chat_but_gate_closed_stays_paper(storage, paper):
    cfg = make_config(live_trading=False, private_key=FAKE_KEY)
    live = LiveTrader(cfg, sdk=FakeSdk)
    r = TradeRouter(storage, paper, live)
    r.storage.set_chat_live("7", True)
    out = r.follow(_alert(), 25.0, chat_id="7")
    assert isinstance(out, PaperFollow)


def test_live_follow_returns_pending_without_session_confirm(storage, paper):
    r = _live_router(storage, paper)
    r.storage.set_chat_live("7", True)
    out = r.follow(_alert(), 25.0, chat_id="7")
    assert isinstance(out, PendingLiveOrder)
    assert "REAL order preview" in out.preview.summary()
    assert r.pending_count() == 1


def test_confirm_pending_executes(storage, paper):
    r = _live_router(storage, paper)
    r.storage.set_chat_live("7", True)
    pending = r.follow(_alert(), 25.0, chat_id="7")
    done = r.confirm_pending(pending.pending_id)
    assert isinstance(done, LiveFollow)
    assert r.pending_count() == 0


def test_cancel_pending(storage, paper):
    r = _live_router(storage, paper)
    r.storage.set_chat_live("7", True)
    pending = r.follow(_alert(), 25.0, chat_id="7")
    assert r.cancel_pending(pending.pending_id)
    assert r.pending_count() == 0
    with pytest.raises(KeyError):
        r.confirm_pending(pending.pending_id)


def test_session_confirm_auto_executes(storage, paper):
    r = _live_router(storage, paper)
    r.storage.set_chat_live("7", True)
    r.confirm_session()
    out = r.follow(_alert(), 25.0, chat_id="7")
    assert isinstance(out, LiveFollow)


def test_live_cap_enforced_on_confirm(storage, paper):
    r = _live_router(storage, paper)  # cap $1000
    r.storage.set_chat_live("7", True)
    r.confirm_session()
    from src.live_trader import OrderTooLarge
    with pytest.raises(OrderTooLarge):
        r.follow(_alert(), 5000.0, chat_id="7")
