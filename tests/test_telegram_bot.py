from unittest.mock import MagicMock

import pytest

from src.models import WhaleAlert
from src.telegram_bot import LIVE_WARNING, TelegramBot
from src.trade_router import PaperFollow
from tests.conftest import make_config, make_trade


def _bot(router, **over):
    cfg = make_config(tg_token="test-token", **over)
    http = MagicMock()
    http.post.return_value.json.return_value = {"ok": True, "result": {}}
    b = TelegramBot(cfg, router, http=http)
    return b, http


def _alert():
    return WhaleAlert(trade=make_trade(usd=50_000, price=0.5, tx="0xabc"),
                      watcher_name="w")


def test_start_sends_help(router):
    b, http = _bot(router)
    b.handle_message("1", "/start")
    assert http.post.called


def test_watch_parses_args(router):
    b, _ = _bot(router)
    b.handle_message("1", "/watch 5000 0.1 0.9")
    ws = router.storage.list_watchers()
    assert any(w.name == "tg-1" and w.min_usd == 5000 for w in ws)


def test_watch_bad_args_usage(router):
    b, http = _bot(router)
    b.handle_message("1", "/watch abc")
    body = http.post.call_args[0][0]
    assert "sendMessage" in body


def test_unwatch(router):
    b, _ = _bot(router)
    b.handle_message("1", "/watch 5000")
    b.handle_message("1", "/unwatch")
    assert not [w for w in router.storage.list_watchers()
                if w.name == "tg-1"]


def test_live_on_refused_when_gate_closed(router):
    b, http = _bot(router)
    b.handle_message("1", "/live on")
    assert not router.storage.chat_live_enabled("1")
    payload = http.post.call_args[1]["json"]
    assert "not available" in payload["text"]


def test_live_on_off_cycle(storage, paper):
    from src.live_trader import LiveTrader
    from src.trade_router import TradeRouter
    from tests.conftest import FAKE_KEY, FakeSdk
    cfg = make_config(tg_token="t", live_trading=True, private_key=FAKE_KEY)
    live = LiveTrader(cfg, sdk=FakeSdk)
    r = TradeRouter(storage, paper, live)
    b, _ = _bot(r)
    b.handle_message("9", "/live on")
    assert r.storage.chat_live_enabled("9")
    b.handle_message("9", "/live off")
    assert not r.storage.chat_live_enabled("9")


def test_live_warning_text_is_scary():
    assert "REAL money" in LIVE_WARNING
    assert "/live off" in LIVE_WARNING


def test_push_alert_includes_follow_buttons(router):
    b, http = _bot(router)
    b.config.tg_default_chat = "1"
    b.push_alert(_alert(), chat_id="1")
    payload = http.post.call_args[1]["json"]
    kb = payload["reply_markup"]["inline_keyboard"][0]
    assert any("paper" in btn["text"] for btn in kb)
    assert any("LIVE" in btn["text"] for btn in kb)


def test_follow_paper_callback(router):
    b, http = _bot(router)
    b.config.tg_default_chat = "1"
    b.push_alert(_alert(), chat_id="1")
    b.handle_callback("1", "follow_paper:0xabc", "cb1")
    assert router.paper.storage.list_positions("open")


def test_follow_live_callback_asks_confirmation(storage, paper):
    from src.live_trader import LiveTrader
    from src.trade_router import TradeRouter
    from tests.conftest import FAKE_KEY, FakeSdk
    cfg = make_config(tg_token="t", live_trading=True, private_key=FAKE_KEY)
    live = LiveTrader(cfg, sdk=FakeSdk)
    r = TradeRouter(storage, paper, live)
    b, http = _bot(r)
    b.config.tg_default_chat = "1"
    r.storage.set_chat_live("1", True)
    b.push_alert(_alert(), chat_id="1")
    b.handle_callback("1", "follow_live:0xabc", "cb1")
    assert r.pending_count() == 1
    texts = [c[1]["json"].get("text", "")
             for c in http.post.call_args_list if "json" in c[1]]
    assert any("CONFIRM REAL ORDER" in t for t in texts)


def test_status_shows_mode(router):
    b, http = _bot(router)
    b.handle_message("1", "/status")
    payload = http.post.call_args[1]["json"]
    assert "paper" in payload["text"].lower()
