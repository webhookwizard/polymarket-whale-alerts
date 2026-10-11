# 🐋 Polymarket Whale Alerts

**Get pinged the second a whale moves on Polymarket — then copy the trade in one tap, on paper or with real money.**

中文说明 → [README_CN.md](README_CN.md)

---

## 👀 See it in action (30 seconds)

```bash
git clone https://github.com/webhookwizard/polymarket-whale-alerts.git
cd polymarket-whale-alerts
pip install -r requirements.txt
python3 demo.py        # no API keys needed — runs a simulated whale tape
```

```
🐋  POLYMARKET WHALE ALERTS — live demo (mock feed, paper mode)
[1/5] Polling mock trade tape (60 synthetic trades)...
      → 1 poll, 21 whale alert(s) detected

[2/5] 📲 Telegram-style alert for the biggest whale:
🐋 WHALE SELL Yes
$237,187 @ 68.6%
NBA: Will the Celtics win the championship?
👤 0xWhale
🔗 Open market

[3/5] Paper-following the whale with $25 (simulated)...
[4/5] 🟢 P&L: $+2.41 on $25 (entry 0.686 → 0.620)
[5/5] Live-trading gate status: mode: PAPER (gate closed — no keys set)
```

Prefer a dashboard over a terminal? `python3 -m src.webapp` → http://127.0.0.1:5000 — whale feed, paper P&L, watcher controls.

---

## 😤 The problem

You trade on Polymarket. The whales — wallets that move $50k+ in a single click — see the flow before the odds move. By the time you notice the price shifted, the edge is gone. You refresh the activity tab like it's a slot machine, miss the move, and tell yourself "next time."

There is no next time. Unless a robot is watching for you.

## ✅ What this does for you

- **Instant whale pings on Telegram** — market, side (Yes/No), size, price, and a link to the market, seconds after the trade prints.
- **Your rules, not noise** — only trades above your size threshold (e.g. $10k+), inside your probability window, on markets you allow (or excluding ones you block).
- **One-tap copy trading** — hit *Follow* on any alert to mirror the whale's side in a **paper account** first; watch entry price, live price, and P&L per position.
- **Real orders when YOU say so** — flip `/live on` in Telegram (or the dashboard toggle) and the same *Follow* button places a real limit order on Polymarket. Off by default. Capped per order. Every live order asks for explicit confirmation.
- **A dashboard you can actually read** — live whale feed, paper positions with P&L, start/stop the watcher, big LIVE vs PAPER badge so you always know which mode you're in.

## ⚡ Try it in 2 minutes

```bash
pip install -r requirements.txt
python3 demo.py
```

That's the whole demo — mock whale tape → alert → paper follow → P&L. No keys, no network, no money.

**Telegram bot** (needs a free bot token from [@BotFather](https://t.me/BotFather)):

```bash
cp .env.example .env        # add TG_BOT_TOKEN=...
TG_DEFAULT_CHAT_ID=123456789 python3 -m src.bot_cli --mock
```

**Dashboard:** `python3 -m src.webapp` → http://127.0.0.1:5000

**Live public feed (read-only, still free):** `python3 -m src.watcher_cli`

### 🪟 On Windows

No `python3` on Windows — use `python` instead. Easiest: download the repo ZIP from GitHub, extract it, and **double-click `start_dashboard.bat`** (installs dependencies on first run, then starts the dashboard). Then open http://127.0.0.1:5000 in your browser.

Manual equivalent:

```bat
pip install -r requirements.txt
python -m src.webapp
```

You need [Python](https://www.python.org/downloads/) installed with **"Add python.exe to PATH"** ticked during setup.

## 🔴 Real-money mode — read this first

This bot **can place real orders** on Polymarket. That means real money, real losses, and a private key that must never leak. The safety rails are not optional:

1. **Paper by default.** Live mode needs BOTH `POLY_LIVE_TRADING=true` **and** `POLY_PRIVATE_KEY` in `.env`. Missing either → everything stays paper, with a log line saying so.
2. **Key hygiene.** The key comes only from the environment. It is never logged, never printed, never written anywhere else. Startup warns if it looks malformed.
3. **Per-order cap.** `POLY_MAX_ORDER_USD` (default **$25**) — any order above it is rejected *before* anything is signed. Lower it for your first tests.
4. **Two-step confirmation.** `/live on` only arms your chat; each live *Follow* shows a dry-run preview ("REAL order preview: BUY 50.0 Yes @ 0.500 ≈ $25.00") and needs a second explicit tap. Dashboard sessions need the confirmation toggle too.
5. **You need Polygon USDC** in the wallet the key controls, plus a little POL for gas. Start with tiny sizes. Keys are never shared — with anyone, including me.

```bash
pip install -r requirements-live.txt   # the official polymarket-client SDK
# .env:
#   POLY_LIVE_TRADING=true
#   POLY_PRIVATE_KEY=0x...        # your Polygon wallet key — .env is gitignored
#   POLY_MAX_ORDER_USD=5           # start tiny
python3 -m src.bot_cli --confirm-live  # then /live on in Telegram
```

To turn it off: `/live off` in Telegram, or unset `POLY_LIVE_TRADING`. The dashboard badge flips back to PAPER immediately.

> ⚠️ **Risk warning:** Trading involves risk of loss. This software is provided as-is; whale-following is not financial advice, and past whale moves don't predict anything. Never trade money you can't afford to lose.

## 🧪 Tests

89 tests, all passing, zero network (the exchange SDK is fully mocked):

```bash
python3 -m pytest tests/ -q
```

Coverage includes the safety rails: gate closed without flag/key → paper; over-cap orders rejected pre-signing; dry-run preview output; private key redaction in logs and exceptions.

<details>
<summary><b>🔧 How it works (for the curious)</b></summary>

- **Feed** — `src/polymarket_client.py` polls Polymarket's public trade tape (`data-api.polymarket.com/trades`) with timeout/retry/backoff; `gamma-api.polymarket.com` for market metadata. `src/mock_feed.py` replays realistic synthetic whales for demo/tests.
- **Watcher** — `src/watcher.py` dedupes by tx hash and matches trades against your rules (`min_usd`, probability window, allow/block lists).
- **Routing** — `src/trade_router.py` sends follows to paper (`src/paper_trader.py`) or live (`src/live_trader.py`). Live orders go through gate → cap → confirmation, in that order, every time.
- **Execution** — `src/live_trader.py` wraps the official `polymarket-client` SDK (`SecureClient.create(private_key=...)`, `place_limit_order(...)`). The SDK is an optional dependency — paper mode never imports it.
- **Interfaces** — `src/telegram_bot.py` (raw Bot API, long-polling), `src/webapp.py` (Flask + vanilla JS + SQLite in `src/storage.py`).
- **Structure** — `src/` (9 modules) · `tests/` (89 tests) · `demo.py` · `.env.example` · `requirements.txt` / `requirements-live.txt`

</details>

---

> **Want this customized?** Whale alerts for your own strategy — custom thresholds, Discord/X/Slack push, auto-follow rules, portfolio tracking.
> DM [@saulgoodmanc99](https://t.me/saulgoodmanc99) — Telegram bots from **$299**, settled in USDT. 50% deposit, 7-day bug warranty.

MIT © Webhook Wizard
