"""Web dashboard: visual operation for the whale watcher.

- LIVE vs PAPER badge in the header (from the live-trading gate).
- Watcher rules: create / delete.
- Live whale feed (polls /api/alerts).
- Paper positions with P&L.
- Follow buttons: paper follows instantly; LIVE follows need the
  session confirmation toggle ON, then a per-order confirm.
- Start/stop the background watcher.

Run: python3 -m src.webapp   (or via the dashboard section of demo.py)
"""
from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify, render_template, request

from .config import Config
from .live_trader import LiveTrader
from .models import WatcherConfig, WhaleAlert
from .paper_trader import PaperTrader
from .polymarket_client import PolymarketClient
from .storage import Storage
from .trade_router import LiveFollow, PaperFollow, PendingLiveOrder, TradeRouter
from .watcher import WhaleWatcher

log = logging.getLogger(__name__)


def create_app(config: Config | None = None,
               router: TradeRouter | None = None,
               watcher: WhaleWatcher | None = None) -> Flask:
    config = config or Config.from_env()
    storage = Storage(config.db_path)
    if router is None:
        paper = PaperTrader(storage,
                            price_fn=PolymarketClient().get_market_price)
        live = LiveTrader(config)
        router = TradeRouter(storage, paper, live)
    if watcher is None:
        stored = storage.list_watchers()
        watcher = WhaleWatcher(
            PolymarketClient(),
            stored or [WatcherConfig(
                name="default",
                min_usd=config.default_min_usd,
                prob_min=config.default_prob_min,
                prob_max=config.default_prob_max,
            )],
            on_alert=lambda a: storage.save_alert(
                a.watcher_name, a.trade.tx_hash, a.trade.market_title,
                a.trade.market_slug, a.trade.side, a.trade.outcome,
                a.trade.usd_value, a.trade.price),
        )

    app = Flask(__name__,
                template_folder="templates",
                static_folder="static")
    app.config["router"] = router
    app.config["watcher"] = watcher
    app.config["app_config"] = config
    app.config["storage"] = storage

    # Recent full alert objects (for follow actions); storage holds the feed.
    recent_alerts: dict[str, WhaleAlert] = {}
    _orig_on_alert = watcher.on_alert

    def _on_alert(alert: WhaleAlert) -> None:
        recent_alerts[alert.trade.tx_hash] = alert
        # keep memory bounded
        if len(recent_alerts) > 500:
            oldest = next(iter(recent_alerts))
            del recent_alerts[oldest]
        if _orig_on_alert:
            _orig_on_alert(alert)

    watcher.on_alert = _on_alert
    app.config["recent_alerts"] = recent_alerts

    def mode_info() -> dict:
        ok, reason = config.live_gate()
        return {
            "mode": "LIVE" if ok else "PAPER",
            "live_armed": ok,
            "gate_reason": reason,
            "max_order_usd": config.max_order_usd,
            "session_confirmed": router.session_confirmed,
            "key_fingerprint": config.key_fingerprint() if ok else None,
        }

    @app.get("/")
    def index():
        return render_template("dashboard.html", mode=mode_info()["mode"])

    @app.get("/api/mode")
    def api_mode():
        return jsonify(mode_info())

    @app.post("/api/session/confirm")
    def api_session_confirm():
        data = request.get_json(force=True, silent=True) or {}
        if data.get("confirmed") is True:
            if not router.live.enabled:
                return jsonify({"ok": False,
                                "error": "live gate closed — cannot confirm"}), 400
            router.confirm_session()
            return jsonify({"ok": True, "session_confirmed": True})
        return jsonify({"ok": False, "error": "pass {\"confirmed\": true}"}), 400

    # -- watchers ---------------------------------------------------------
    @app.get("/api/watchers")
    def api_watchers():
        return jsonify([
            {"name": w.name, "min_usd": w.min_usd,
             "prob_min": w.prob_min, "prob_max": w.prob_max,
             "allow_slugs": w.allow_slugs, "block_slugs": w.block_slugs,
             "enabled": w.enabled}
            for w in storage.list_watchers()
        ])

    @app.post("/api/watchers")
    def api_add_watcher():
        data = request.get_json(force=True, silent=True) or {}
        try:
            w = WatcherConfig(
                name=str(data.get("name", "custom")).strip() or "custom",
                min_usd=float(data.get("min_usd", config.default_min_usd)),
                prob_min=float(data.get("prob_min", config.default_prob_min)),
                prob_max=float(data.get("prob_max", config.default_prob_max)),
                allow_slugs=list(data.get("allow_slugs", [])),
                block_slugs=list(data.get("block_slugs", [])),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        storage.save_watcher(w)
        watcher.watchers = storage.list_watchers() or watcher.watchers
        return jsonify({"ok": True, "name": w.name})

    @app.delete("/api/watchers/<name>")
    def api_del_watcher(name: str):
        ok = storage.delete_watcher(name)
        watcher.watchers = storage.list_watchers()
        if not watcher.watchers:
            watcher.watchers = [WatcherConfig()]
        return jsonify({"ok": ok})

    @app.get("/api/watcher/state")
    def api_watcher_state():
        return jsonify({"running": watcher.running,
                        "polls": watcher.polls,
                        "alerts": watcher.alerts_emitted})

    @app.post("/api/watcher/start")
    def api_watcher_start():
        if watcher.running:
            return jsonify({"ok": True, "already": True})
        t = threading.Thread(
            target=watcher.run,
            kwargs={"interval_sec": config.poll_interval_sec},
            daemon=True)
        t.start()
        return jsonify({"ok": True})

    @app.post("/api/watcher/stop")
    def api_watcher_stop():
        watcher.stop()
        return jsonify({"ok": True})

    # -- alerts feed --------------------------------------------------------
    @app.get("/api/alerts")
    def api_alerts():
        limit = min(int(request.args.get("limit", 30)), 100)
        return jsonify(storage.recent_alerts(limit))

    # -- paper positions ------------------------------------------------------
    @app.get("/api/positions")
    def api_positions():
        out = []
        for p in router.paper.storage.list_positions():
            cur = router.paper.current_price(p.token_id)
            out.append({
                "id": p.id, "market_title": p.market_title,
                "side": p.side, "outcome": p.outcome,
                "entry_price": p.entry_price, "size_usd": p.size_usd,
                "status": p.status,
                "current_price": cur,
                "pnl_usd": p.pnl_usd(cur) if cur else None,
            })
        return jsonify(out)

    @app.post("/api/positions/<int:pos_id>/close")
    def api_close_position(pos_id: int):
        ok = router.paper.close_position(pos_id)
        return jsonify({"ok": ok})

    # -- follow --------------------------------------------------------------
    @app.post("/api/follow")
    def api_follow():
        """Follow the latest alert for a market. Body:
        {"tx_hash": ..., "size_usd": 25, "mode": "paper"|"live",
         "confirmed": true}  — live needs session confirmation first
        (POST /api/session/confirm) and then confirmed:true per order.
        """
        data = request.get_json(force=True, silent=True) or {}
        tx_hash = data.get("tx_hash", "")
        size_usd = float(data.get("size_usd", 25))
        mode = data.get("mode", "paper")
        confirmed = bool(data.get("confirmed", False))

        alert = _find_alert(tx_hash, recent_alerts)
        if alert is None:
            return jsonify({"ok": False,
                            "error": "alert not found (tx_hash unknown or expired)"}), 404

        chat_live = (mode == "live")
        # Temporarily treat dashboard as a "chat" with live flag = mode.
        orig = router.storage.chat_live_enabled("__dashboard__")
        router.storage.set_chat_live("__dashboard__", chat_live)
        try:
            if mode == "live":
                if not router.live.enabled:
                    ok, reason = config.live_gate()
                    return jsonify({"ok": False, "error": reason}), 400
                if not (router.session_confirmed or confirmed):
                    pending = router.follow(alert, size_usd,
                                            chat_id="__dashboard__")
                    assert isinstance(pending, PendingLiveOrder)
                    return jsonify({
                        "ok": True, "needs_confirmation": True,
                        "pending_id": pending.pending_id,
                        "preview": _preview_json(pending.preview),
                    })
                result = router.follow(alert, size_usd,
                                       chat_id="__dashboard__",
                                       auto_confirm=True)
            else:
                result = router.follow(alert, size_usd, chat_id=None)
        finally:
            router.storage.set_chat_live("__dashboard__", orig)

        if isinstance(result, PaperFollow):
            return jsonify({"ok": True, "mode": "paper",
                            "position_id": result.position.id})
        if isinstance(result, LiveFollow):
            return jsonify({"ok": True, "mode": "live",
                            "preview": _preview_json(result.preview)})
        return jsonify({"ok": False, "error": "unexpected result"}), 500

    @app.post("/api/follow/confirm/<pending_id>")
    def api_confirm_follow(pending_id: str):
        try:
            result = router.confirm_pending(pending_id)
        except KeyError:
            return jsonify({"ok": False,
                            "error": "pending order expired"}), 404
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "mode": "live",
                        "preview": _preview_json(result.preview)})

    return app


def _preview_json(p) -> dict:
    return {"token_id": p.token_id, "market_title": p.market_title,
            "side": p.side, "outcome": p.outcome, "price": p.price,
            "size_shares": p.size_shares, "usd_value": p.usd_value,
            "summary": p.summary()}


def _find_alert(tx_hash: str, recent: dict):
    return recent.get(tx_hash)


def main() -> None:
    import argparse
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO,
                         format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Whale alerts web dashboard")
    ap.add_argument("--confirm-live", action="store_true",
                    help="Pre-confirm this session for LIVE orders "
                         "(still requires POLY_LIVE_TRADING=true + key + cap)")
    args = ap.parse_args()

    config = Config.from_env()
    app = create_app(config)
    if args.confirm_live:
        app.config["router"].confirm_session()
        _logging.warning("Session LIVE-confirmed via --confirm-live")
    ok, reason = config.live_gate()
    _logging.info("Dashboard starting in %s mode: %s",
                  "LIVE" if ok else "PAPER", reason)
    app.run(host=config.web_host, port=config.web_port)


if __name__ == "__main__":
    main()
