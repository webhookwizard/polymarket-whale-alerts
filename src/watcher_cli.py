"""CLI: run the whale watcher against the live public feed (or --mock).

    python3 -m src.watcher_cli [--mock] [--min-usd 10000]

Alerts print to stdout. Pair with the Telegram bot or dashboard for push.
"""
import argparse
import logging

from .config import Config
from .mock_feed import MockFeed
from .models import WatcherConfig
from .polymarket_client import PolymarketClient
from .storage import Storage
from .watcher import WhaleWatcher

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser(description="Polymarket whale watcher")
    ap.add_argument("--mock", action="store_true",
                    help="use synthetic feed (no network)")
    ap.add_argument("--min-usd", type=float, default=None)
    ap.add_argument("--max-polls", type=int, default=None,
                    help="stop after N polls (default: run forever)")
    args = ap.parse_args()

    config = Config.from_env()
    feed = MockFeed() if args.mock else PolymarketClient()
    storage = Storage(config.db_path)

    stored = storage.list_watchers()
    watchers = stored or [WatcherConfig(
        name="default",
        min_usd=args.min_usd or config.default_min_usd,
        prob_min=config.default_prob_min,
        prob_max=config.default_prob_max,
    )]

    def on_alert(alert):
        print("🐋", alert.headline(), flush=True)
        storage.save_alert(alert.watcher_name, alert.trade.tx_hash,
                           alert.trade.market_title, alert.trade.market_slug,
                           alert.trade.side, alert.trade.outcome,
                           alert.trade.usd_value, alert.trade.price)

    watcher = WhaleWatcher(feed, watchers, on_alert=on_alert)
    mode = "MOCK" if args.mock else "LIVE public feed"
    print(f"Watching ({mode}), {len(watchers)} rule(s). Ctrl-C to stop.")
    watcher.run(interval_sec=config.poll_interval_sec,
                max_polls=args.max_polls)


if __name__ == "__main__":
    main()
