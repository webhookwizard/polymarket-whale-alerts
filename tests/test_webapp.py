import pytest

from src.live_trader import LiveTrader
from src.models import WhaleAlert, WatcherConfig
from src.paper_trader import PaperTrader
from src.storage import Storage
from src.trade_router import TradeRouter
from src.watcher import WhaleWatcher
from src.webapp import create_app
from tests.conftest import FAKE_KEY, FakeSdk, make_config, make_trade


class ListFeed:
    def get_trades(self, limit=60):
        return []


def _app(live_on=False):
    cfg = make_config(db_path=":memory:", live_trading=live_on,
                      private_key=FAKE_KEY if live_on else "")
    storage = Storage(":memory:")
    paper = PaperTrader(storage, price_fn=lambda t: 0.6)
    live = LiveTrader(cfg, sdk=FakeSdk)
    router = TradeRouter(storage, paper, live)
    watcher = WhaleWatcher(ListFeed(), [WatcherConfig()])
    app = create_app(cfg, router, watcher)
    app.config["TESTING"] = True
    return app, router


def test_index_renders_paper_badge():
    app, _ = _app()
    html = app.test_client().get("/").data.decode()
    assert "PAPER" in html


def test_mode_endpoint():
    app, _ = _app()
    m = app.test_client().get("/api/mode").get_json()
    assert m["mode"] == "PAPER"
    assert not m["live_armed"]


def test_mode_live_when_gate_open():
    app, _ = _app(live_on=True)
    m = app.test_client().get("/api/mode").get_json()
    assert m["mode"] == "LIVE"
    assert m["key_fingerprint"] != FAKE_KEY  # redacted


def test_watcher_crud():
    app, _ = _app()
    c = app.test_client()
    r = c.post("/api/watchers", json={"name": "w1", "min_usd": 5000})
    assert r.get_json()["ok"]
    assert any(w["name"] == "w1" for w in c.get("/api/watchers").get_json())
    assert c.delete("/api/watchers/w1").get_json()["ok"]


def test_follow_paper():
    app, router = _app()
    c = app.test_client()
    alert = WhaleAlert(trade=make_trade(tx="0xdash"), watcher_name="w")
    app.config["recent_alerts"]["0xdash"] = alert
    r = c.post("/api/follow", json={"tx_hash": "0xdash", "mode": "paper"})
    body = r.get_json()
    assert body["ok"] and body["mode"] == "paper"


def test_follow_unknown_alert_404():
    app, _ = _app()
    r = app.test_client().post("/api/follow",
                               json={"tx_hash": "0xnope", "mode": "paper"})
    assert r.status_code == 404


def test_live_follow_needs_session_confirm():
    app, router = _app(live_on=True)
    c = app.test_client()
    alert = WhaleAlert(trade=make_trade(tx="0xlive"), watcher_name="w")
    app.config["recent_alerts"]["0xlive"] = alert
    r = c.post("/api/follow",
               json={"tx_hash": "0xlive", "mode": "live", "size_usd": 10})
    body = r.get_json()
    assert body["ok"] and body["needs_confirmation"]
    assert "REAL order preview" in body["preview"]["summary"]


def test_session_confirm_then_live_follow():
    app, router = _app(live_on=True)
    c = app.test_client()
    alert = WhaleAlert(trade=make_trade(tx="0xlive2"), watcher_name="w")
    app.config["recent_alerts"]["0xlive2"] = alert
    r = c.post("/api/session/confirm", json={"confirmed": True})
    assert r.get_json()["ok"]
    r = c.post("/api/follow",
               json={"tx_hash": "0xlive2", "mode": "live", "size_usd": 10,
                     "confirmed": True})
    body = r.get_json()
    assert body["ok"] and body["mode"] == "live"


def test_session_confirm_refused_in_paper():
    app, _ = _app()
    r = app.test_client().post("/api/session/confirm",
                               json={"confirmed": True})
    assert r.status_code == 400


def test_positions_endpoint():
    app, router = _app()
    c = app.test_client()
    alert = WhaleAlert(trade=make_trade(tx="0xpos"), watcher_name="w")
    app.config["recent_alerts"]["0xpos"] = alert
    c.post("/api/follow", json={"tx_hash": "0xpos", "mode": "paper"})
    ps = c.get("/api/positions").get_json()
    assert len(ps) == 1 and "pnl_usd" in ps[0]
