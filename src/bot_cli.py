"""CLI: run the Telegram bot + background watcher.

    TG_BOT_TOKEN=... TG_DEFAULT_CHAT_ID=... python3 -m src.bot_cli [--mock]

Live-trading session confirmation:
    python3 -m src.bot_cli --confirm-live
(still requires POLY_LIVE_TRADING=true + POLY_PRIVATE_KEY + cap)
"""
import argparse
import logging
import threading

from .config import Config
from .live_trader import LiveTrader
from .mock_feed import MockFeed
from .models import WatcherConfig
from .paper_trader import PaperTrader
from .polymarket_client import PolymarketClient
from .storage import Storage
from .telegram_bot import TelegramBot
from .trade_router import TradeRouter
from .watcher import WhaleWatcher

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="Whale alerts Telegram bot")
    ap.add_argument("--mock", action="store_true",
                    help="synthetic feed instead of the live public tape")
    ap.add_argument("--confirm-live", action="store_true",
                    help="pre-confirm this session for LIVE orders")
    args = ap.parse_args()

    config = Config.from_env()
    if not config.tg_token:
        raise SystemExit("Set TG_BOT_TOKEN in .env first (see .env.example)")

    storage = Storage(config.db_path)
    feed = MockFeed() if args.mock else PolymarketClient()
    stored = storage.list_watchers()
    watchers = stored or [WatcherConfig(
        name="default", min_usd=config.default_min_usd,
        prob_min=config.default_prob_min, prob_max=config.default_prob_max)]

    paper = PaperTrader(storage, price_fn=PolymarketClient().get_market_price)
    live = LiveTrader(config)
    router = TradeRouter(storage, paper, live)
    if args.confirm_live:
        router.confirm_session()
        log.warning("Session LIVE-confirmed via --confirm-live")

    bot = TelegramBot(config, router)
    watcher = WhaleWatcher(feed, watchers, on_alert=bot.push_alert)
    bot.watcher = watcher

    t = threading.Thread(
        target=watcher.run,
        kwargs={"interval_sec": config.poll_interval_sec},
        daemon=True)
    t.start()
    ok, reason = config.live_gate()
    log.info("Bot starting in %s mode: %s", "LIVE" if ok else "PAPER", reason)
    bot.run()


if __name__ == "__main__":
    main()
