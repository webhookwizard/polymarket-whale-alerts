#!/usr/bin/env python3
"""One-command end-to-end demo. ZERO api keys, ZERO network, ZERO money.

    python3 demo.py

What it does:
  1. Spins up a mock trade feed (realistic synthetic whale trades).
  2. Runs the whale watcher -> prints Telegram-style alerts.
  3. Paper-follows the biggest whale -> tracks a simulated position.
  4. Refreshes the price (mocked) and shows P&L.
  5. Prints how to launch the web dashboard and the real watcher.

Live trading is NOT touched: the gate stays closed without
POLY_LIVE_TRADING=true + POLY_PRIVATE_KEY (see the demo output).
"""
import logging
import sys

sys.path.insert(0, ".")

from src.config import Config
from src.live_trader import LiveTrader
from src.mock_feed import MockFeed
from src.models import WatcherConfig
from src.paper_trader import PaperTrader
from src.storage import Storage
from src.trade_router import PaperFollow, TradeRouter
from src.watcher import WhaleWatcher

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def main() -> None:
    print("=" * 64)
    print("🐋  POLYMARKET WHALE ALERTS — live demo (mock feed, paper mode)")
    print("=" * 64)

    config = Config.from_env()
    storage = Storage(":memory:")
    paper = PaperTrader(storage, price_fn=lambda token_id: 0.62)  # mocked price
    live = LiveTrader(config)
    router = TradeRouter(storage, paper, live)

    alerts = []
    watcher = WhaleWatcher(
        MockFeed(seed=7, whale_probability=0.35),
        [WatcherConfig(name="demo", min_usd=10_000,
                       prob_min=0.05, prob_max=0.95)],
        on_alert=alerts.append,
    )

    print("\n[1/5] Polling mock trade tape (60 synthetic trades)...")
    watcher.poll_once(limit=60)
    print(f"      → {watcher.polls} poll, {len(alerts)} whale alert(s) detected")

    if not alerts:
        print("      (no whales this run — re-run; the feed is randomized)")
        return
    biggest = max(alerts, key=lambda a: a.trade.usd_value)

    print("\n[2/5] 📲 Telegram-style alert for the biggest whale:")
    print("-" * 64)
    print(biggest.trade.tx_hash and _strip_html(biggest.format_telegram()))
    print("-" * 64)

    print("\n[3/5] Paper-following the whale with $25 (simulated)...")
    result = router.follow(biggest, 25.0)
    assert isinstance(result, PaperFollow)
    pos = result.position
    print(f"      → paper position #{pos.id}: {pos.side} {pos.outcome} "
          f"${pos.size_usd:.0f} @ {pos.entry_price:.3f}")

    print("\n[4/5] Market moved — P&L check (mocked current price 0.62):")
    pnl = paper.pnl(pos)
    arrow = "🟢" if (pnl or 0) >= 0 else "🔴"
    print(f"      {arrow} P&L: ${pnl:+.2f} on ${pos.size_usd:.0f} "
          f"(entry {pos.entry_price:.3f} → 0.620)")

    print("\n[5/5] Live-trading gate status:")
    ok, reason = config.live_gate()
    print(f"      mode: {'LIVE' if ok else 'PAPER'} — {reason}")
    print("      (set POLY_LIVE_TRADING=true + POLY_PRIVATE_KEY to arm; "
          "demo never does)")

    print("\n" + "=" * 64)
    print("Next steps:")
    print("  Web dashboard : python3 -m src.webapp      # then open http://127.0.0.1:5000")
    print("  Real watcher  : python3 -m src.watcher_cli  # polls the live public feed")
    print("  Telegram bot  : TG_BOT_TOKEN=... python3 -m src.bot_cli")
    print("=" * 64)


def _strip_html(s: str) -> str:
    import re
    s = re.sub(r"<[^>]+>", "", s)
    return s


if __name__ == "__main__":
    main()
