from src.models import PaperPosition, WatcherConfig


def test_watcher_crud(storage):
    storage.save_watcher(WatcherConfig(name="w1", min_usd=5000))
    ws = storage.list_watchers()
    assert len(ws) == 1 and ws[0].min_usd == 5000
    storage.save_watcher(WatcherConfig(name="w1", min_usd=7000))  # upsert
    assert storage.list_watchers()[0].min_usd == 7000
    assert storage.delete_watcher("w1")
    assert storage.list_watchers() == []
    assert not storage.delete_watcher("nope")


def test_alert_dedupe(storage):
    ok1 = storage.save_alert("w", "0xh", "M", "m", "BUY", "Yes", 100.0, 0.5)
    ok2 = storage.save_alert("w", "0xh", "M", "m", "BUY", "Yes", 100.0, 0.5)
    assert ok1 and not ok2
    assert len(storage.recent_alerts()) == 1


def test_paper_position_lifecycle(storage):
    pid = storage.open_paper_position(PaperPosition(
        market_title="M", token_id="t", side="BUY", outcome="Yes",
        entry_price=0.5, size_usd=25))
    p = storage.get_position(pid)
    assert p.status == "open"
    assert storage.close_paper_position(pid, 0.6)
    assert storage.get_position(pid).status == "closed"
    assert not storage.close_paper_position(pid, 0.7)  # already closed


def test_chat_live_flag(storage):
    assert not storage.chat_live_enabled("123")
    storage.set_chat_live("123", True)
    assert storage.chat_live_enabled("123")
    storage.set_chat_live("123", False)
    assert not storage.chat_live_enabled("123")
