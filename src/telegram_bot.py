"""Telegram bot: real-time whale push alerts + follow buttons.

Raw Bot API over requests (no heavy framework). Fully unit-tested
with a mocked HTTP layer; without TG_BOT_TOKEN the module imports
fine and the watcher/dashboard still work.

Commands: /start /watch /unwatch /list /status /live /help
Inline buttons on alerts: [Follow $X (paper)] [Follow $X (LIVE)]
LIVE follows ask for explicit confirmation before anything is signed.
"""
from __future__ import annotations

import logging
import time

import requests

from .config import Config
from .models import WhaleAlert
from .trade_router import LiveFollow, PaperFollow, PendingLiveOrder, TradeRouter
from .watcher import WhaleWatcher

log = logging.getLogger(__name__)

LIVE_WARNING = (
    "⚠️ <b>LIVE TRADING ENABLED for this chat</b> ⚠️\n\n"
    "The <b>Follow (LIVE)</b> button will now place <b>REAL orders</b> "
    "with <b>REAL money</b> on Polymarket from your wallet.\n"
    "Every order still needs your tap to confirm, and no single order "
    "can exceed your configured cap.\n\n"
    "Reply /live off to go back to paper mode at any time."
)


class TelegramBot:
    def __init__(self, config: Config, router: TradeRouter,
                 watcher: WhaleWatcher | None = None,
                 http: requests.Session | None = None) -> None:
        self.config = config
        self.router = router
        self.watcher = watcher
        self.http = http or requests.Session()
        self.base = f"https://api.telegram.org/bot{config.tg_token}"
        self.offset = 0
        self.running = False
        self._recent_alerts: dict = {}

    # -- low-level API -----------------------------------------------------
    def _api(self, method: str, **params):
        if not self.config.tg_token:
            raise RuntimeError("TG_BOT_TOKEN is not set")
        resp = self.http.post(f"{self.base}/{method}", json=params, timeout=30)
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data["result"]

    def send(self, chat_id, text: str, reply_markup: dict | None = None,
             parse_mode: str = "HTML") -> None:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                   "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._api("sendMessage", **payload)

    # -- alerts --------------------------------------------------------------
    def push_alert(self, alert: WhaleAlert, chat_id: str | None = None) -> None:
        chat_id = chat_id or self.config.tg_default_chat
        if not chat_id:
            log.warning("No chat to push alert to (TG_DEFAULT_CHAT_ID unset)")
            return
        size = self.follow_size_usd()
        kb = {"inline_keyboard": [[
            {"text": f"📄 Follow ${size:g} (paper)",
             "callback_data": f"follow_paper:{alert.trade.tx_hash}"},
            {"text": f"⚡ Follow ${size:g} (LIVE)",
             "callback_data": f"follow_live:{alert.trade.tx_hash}"},
        ]]}
        self.send(chat_id, alert.format_telegram(), reply_markup=kb)
        # stash the alert so callbacks can resolve it
        self._recent_alerts[alert.trade.tx_hash] = alert

    def follow_size_usd(self) -> float:
        """Quick-follow size — never above the live order cap."""
        return min(25.0, self.router.live.config.max_order_usd)

    # -- commands --------------------------------------------------------------
    def handle_message(self, chat_id: str, text: str) -> None:
        text = (text or "").strip()
        cmd, _, arg = text.partition(" ")
        handler = {
            "/start": self.cmd_start,
            "/help": self.cmd_help,
            "/watch": self.cmd_watch,
            "/unwatch": self.cmd_unwatch,
            "/list": self.cmd_list,
            "/status": self.cmd_status,
            "/live": self.cmd_live,
        }.get(cmd.split("@")[0])
        if handler:
            handler(chat_id, arg.strip())
        # unknown text: ignore quietly (alerts channel style)

    def cmd_start(self, chat_id: str, arg: str) -> None:
        self.send(chat_id,
                  "🐋 <b>Polymarket Whale Alerts</b>\n"
                  "I watch the public trade tape and ping you when a whale moves.\n\n"
                  "/watch — create an alert rule\n"
                  "/list — your rules\n"
                  "/status — paper P&L + mode\n"
                  "/live — real-money mode (default OFF)\n"
                  "/help — all commands")

    def cmd_help(self, chat_id: str, arg: str) -> None:
        self.cmd_start(chat_id, arg)

    def cmd_watch(self, chat_id: str, arg: str) -> None:
        """/watch [min_usd] [prob_min] [prob_max] — e.g. /watch 5000 0.1 0.9"""
        from .models import WatcherConfig
        parts = arg.split()
        try:
            min_usd = float(parts[0]) if len(parts) > 0 else self.config.default_min_usd
            pmin = float(parts[1]) if len(parts) > 1 else self.config.default_prob_min
            pmax = float(parts[2]) if len(parts) > 2 else self.config.default_prob_max
        except ValueError:
            self.send(chat_id, "Usage: /watch [min_usd] [prob_min] [prob_max]\n"
                               "Example: /watch 5000 0.1 0.9")
            return
        name = f"tg-{chat_id}"
        self.router.storage.save_watcher(WatcherConfig(
            name=name, min_usd=min_usd, prob_min=pmin, prob_max=pmax))
        self._sync_watchers()
        self.send(chat_id,
                  f"✅ Watching: trades ≥ ${min_usd:,.0f}, "
                  f"probability {pmin:.0%}–{pmax:.0%}")

    def cmd_unwatch(self, chat_id: str, arg: str) -> None:
        ok = self.router.storage.delete_watcher(f"tg-{chat_id}")
        self._sync_watchers()
        self.send(chat_id, "🛑 Watcher removed." if ok else "No watcher to remove.")

    def cmd_list(self, chat_id: str, arg: str) -> None:
        watchers = self.router.storage.list_watchers()
        if not watchers:
            self.send(chat_id, "No watchers yet. Try /watch 10000")
            return
        lines = ["📋 <b>Watchers</b>"]
        for w in watchers:
            state = "🟢" if w.enabled else "⚪"
            lines.append(f"{state} <b>{w.name}</b>: ≥${w.min_usd:,.0f}, "
                         f"{w.prob_min:.0%}–{w.prob_max:.0%}")
        self.send(chat_id, "\n".join(lines))

    def cmd_status(self, chat_id: str, arg: str) -> None:
        s = self.router.paper.summary()
        live_on = self.router.chat_live(chat_id)
        gate = "🟢 armed" if self.router.live.enabled else "⚪ paper"
        self.send(chat_id,
                  f"📊 <b>Status</b>\n"
                  f"Mode: {'<b>LIVE</b> ' + gate if live_on else 'paper ' + gate}\n"
                  f"Open paper positions: {s['open']}\n"
                  f"Closed: {s['closed']} (realized ${s['realized_pnl_usd']:,.2f})")

    def cmd_live(self, chat_id: str, arg: str) -> None:
        """/live on|off — flip this chat between paper and real orders."""
        arg = arg.lower()
        if arg == "on":
            if not self.router.live.enabled:
                ok, reason = self.router.live.config.live_gate()
                self.send(chat_id,
                          "⛔ <b>Live mode is not available.</b>\n"
                          f"{reason}\n\n"
                          "To enable: set POLY_LIVE_TRADING=true and "
                          "POLY_PRIVATE_KEY in your .env, then restart.")
                return
            self.router.storage.set_chat_live(chat_id, True)
            self.send(chat_id, LIVE_WARNING)
            log.info("Chat %s enabled LIVE trading", chat_id)
        elif arg == "off":
            self.router.storage.set_chat_live(chat_id, False)
            self.send(chat_id, "✅ Back to paper mode. No real orders will be placed.")
        else:
            state = "ON" if self.router.chat_live(chat_id) else "OFF"
            self.send(chat_id, f"Live trading for this chat: <b>{state}</b>\n"
                               "Usage: /live on | /live off")

    # -- callbacks ---------------------------------------------------------------
    def handle_callback(self, chat_id: str, data: str, callback_id: str) -> None:
        action, _, tx_hash = data.partition(":")
        alert = self._recent_alerts.get(tx_hash)
        if not alert:
            self._answer(callback_id, "Alert expired — wait for the next whale 🐋")
            return
        if action == "follow_paper":
            size = self.follow_size_usd()
            result = self.router.follow(alert, size, chat_id=chat_id)
            assert isinstance(result, PaperFollow)
            self._answer(callback_id, f"Paper-followed ${size:g} (pos #{result.position.id})")
            self.send(chat_id,
                      f"📄 Paper position #{result.position.id}: "
                      f"{alert.trade.side} {alert.trade.outcome} "
                      f"${size:g} @ {alert.trade.price:.3f}")
        elif action == "follow_live":
            size = self.follow_size_usd()
            result = self.router.follow(alert, size, chat_id=chat_id)
            if isinstance(result, PaperFollow):
                self._answer(callback_id, "Live not enabled — paper-followed instead")
            elif isinstance(result, PendingLiveOrder):
                kb = {"inline_keyboard": [[
                    {"text": "✅ Confirm REAL order",
                     "callback_data": f"confirm_live:{result.pending_id}"},
                    {"text": "❌ Cancel",
                     "callback_data": f"cancel_live:{result.pending_id}"},
                ]]}
                self.send(chat_id,
                          "⚠️ <b>CONFIRM REAL ORDER</b> ⚠️\n"
                          f"{result.preview.summary()}\n\n"
                          "This spends REAL money. Tap confirm only if you mean it.",
                          reply_markup=kb)
                self._answer(callback_id, "Check the confirmation message ☝️")
        elif action == "confirm_live":
            try:
                live = self.router.confirm_pending(tx_hash)
            except KeyError:
                self._answer(callback_id, "Order expired or already handled")
                return
            except Exception as exc:
                self._answer(callback_id, f"Order failed: {exc}")
                return
            self._answer(callback_id, "✅ REAL order placed")
            self.send(chat_id,
                      f"⚡ <b>LIVE order placed</b>\n{live.preview.summary()}")
        elif action == "cancel_live":
            self.router.cancel_pending(tx_hash)
            self._answer(callback_id, "Cancelled — nothing was signed")

    def _answer(self, callback_id: str, text: str) -> None:
        try:
            self._api("answerCallbackQuery",
                      callback_query_id=callback_id, text=text)
        except Exception:
            pass

    def _sync_watchers(self) -> None:
        if self.watcher is not None:
            from .models import WatcherConfig
            stored = self.router.storage.list_watchers()
            if stored:
                self.watcher.watchers = stored

    # -- main loop ---------------------------------------------------------------
    def run(self) -> None:
        if not self.config.tg_token:
            raise RuntimeError("TG_BOT_TOKEN is not set — cannot start bot")
        self.running = True
        log.info("Telegram bot polling started")
        while self.running:
            try:
                updates = self._api("getUpdates", offset=self.offset, timeout=25)
            except Exception as exc:
                log.warning("getUpdates failed: %s", exc)
                time.sleep(5)
                continue
            for upd in updates:
                self.offset = max(self.offset, upd["update_id"] + 1)
                try:
                    if "message" in upd and "text" in upd["message"]:
                        m = upd["message"]
                        self.handle_message(str(m["chat"]["id"]), m["text"])
                    elif "callback_query" in upd:
                        cb = upd["callback_query"]
                        self.handle_callback(str(cb["message"]["chat"]["id"]),
                                             cb.get("data", ""), cb["id"])
                except Exception as exc:
                    log.warning("update handling failed: %s", exc)

    def stop(self) -> None:
        self.running = False
