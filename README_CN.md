# 🐋 Polymarket 鲸鱼异动提醒

**鲸鱼在 Polymarket 上一动，你的 Telegram 秒收到推送 —— 一键跟单，先模拟盘练手，开了实盘就下真单。**

English → [README.md](README.md)

---

## 👀 30 秒看懂

```bash
git clone https://github.com/webhookwizard/polymarket-whale-alerts.git
cd polymarket-whale-alerts
pip install -r requirements.txt
python3 demo.py        # 零 API key —— 跑的是模拟鲸鱼数据
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

想要可视化？`python3 -m src.webapp` → http://127.0.0.1:5000 —— 鲸鱼动态流、模拟持仓盈亏、监控开关都在里面。

---

## 😤 痛点

你在 Polymarket 上做交易。鲸鱼 —— 一笔就砸 5 万美金以上的钱包 —— 总是比赔率变动先一步看到资金流。等你发现价格动了，肉已经被吃完了。你像刷老虎机一样刷 activity 页面，错过行情，然后安慰自己"下次一定"。

没有下次。除非有个机器人在替你盯盘。

## ✅ 它能帮你

- **Telegram 秒级鲸鱼推送** —— 市场、方向（Yes/No）、金额、价格、市场链接，交易上链几秒后就到。
- **规则你定，不吵你** —— 只推超过你设的金额（比如 1 万美金以上）、在你设的概率区间内、你允许的市场（或排除你拉黑的）。
- **一键跟单** —— 任何一条提醒点 *Follow*，先在**模拟盘**里镜像鲸鱼的方向；每笔持仓的入场价、现价、盈亏都看得见。
- **你点头才动真钱** —— Telegram 里 `/live on`（或网页端开关）之后，同一个 *Follow* 按钮才会在 Polymarket 下真实限价单。默认关闭、单笔限额、每笔都要你二次确认。
- **看得懂的面板** —— 鲸鱼实时流、模拟持仓盈亏、监控启停，顶部大大的 LIVE / PAPER 徽章，永远知道自己在哪个模式。

## ⚡ 2 分钟上手

```bash
pip install -r requirements.txt
python3 demo.py
```

就这么多 —— 模拟鲸鱼流 → 提醒 → 模拟跟单 → 盈亏。不用 key、不用联网、不花钱。

**Telegram 机器人**（需要 [@BotFather](https://t.me/BotFather) 免费申请 token）：

```bash
cp .env.example .env        # 填 TG_BOT_TOKEN=...
TG_DEFAULT_CHAT_ID=123456789 python3 -m src.bot_cli --mock
```

**网页面板：** `python3 -m src.webapp` → http://127.0.0.1:5000

**真实公开数据（只读，免费）：** `python3 -m src.watcher_cli`

## 🔴 实盘模式 —— 先读完这段

这个机器人**真的可以下单**。真钱、真亏损、私钥绝不能泄露。安全护栏不是摆设：

1. **默认模拟盘。** 实盘需要 `.env` 里同时有 `POLY_LIVE_TRADING=true` **和** `POLY_PRIVATE_KEY`。缺一个 → 全部保持模拟，并打日志说明。
2. **私钥只从环境变量来。** 不打日志、不打印、不写到任何别的地方。启动时会检查格式，畸形就警告。
3. **单笔限额。** `POLY_MAX_ORDER_USD`（默认 **25 美金**）—— 超过限额的单子在签名前就被拒掉。第一次测试请调得更小。
4. **两步确认。** `/live on` 只是给这个聊天"解锁"；每次实盘 *Follow* 都会先给你看 dry-run 预览（"REAL order preview: BUY 50.0 Yes @ 0.500 ≈ $25.00"），再点一次确认才执行。网页端也要先打开 session 确认开关。
5. **钱包里要有 Polygon 链上的 USDC**，再备一点 POL 当 gas。先小额测试。私钥不分享给任何人 —— 包括我。

```bash
pip install -r requirements-live.txt   # 官方 polymarket-client SDK
# .env:
#   POLY_LIVE_TRADING=true
#   POLY_PRIVATE_KEY=0x...        # 你的 Polygon 钱包私钥 —— .env 已 gitignore
#   POLY_MAX_ORDER_USD=5           # 先从小额开始
python3 -m src.bot_cli --confirm-live  # 然后在 Telegram 里 /live on
```

关闭实盘：Telegram 里 `/live off`，或删掉 `POLY_LIVE_TRADING`。面板徽章立刻变回 PAPER。

> ⚠️ **风险提示：** 交易有亏损风险。本软件按"现状"提供；跟单鲸鱼不是投资建议，鲸鱼过去的动作不代表未来。只用亏得起的钱。

## 🧪 测试

89 个测试全过，零网络（交易所 SDK 全部 mock）：

```bash
python3 -m pytest tests/ -q
```

安全护栏全覆盖：没 flag/key 就进不了实盘、超限额签名前被拒、dry-run 预览输出、日志和异常里私钥脱敏。

<details>
<summary><b>🔧 技术实现（给好奇的你）</b></summary>

- **数据源** — `src/polymarket_client.py` 轮询 Polymarket 公开交易流（`data-api.polymarket.com/trades`），带超时/重试/退避；`gamma-api.polymarket.com` 查市场信息。`src/mock_feed.py` 给 demo 和测试提供模拟鲸鱼数据。
- **监控** — `src/watcher.py` 按 tx hash 去重，按你的规则（`min_usd`、概率区间、允许/拉黑名单）过滤。
- **路由** — `src/trade_router.py` 把跟单送往模拟盘（`src/paper_trader.py`）或实盘（`src/live_trader.py`）。实盘每次都走 门控 → 限额 → 确认 三道关。
- **下单** — `src/live_trader.py` 封装官方 `polymarket-client` SDK（`SecureClient.create(private_key=...)`、`place_limit_order(...)`）。SDK 是可选依赖 —— 模拟盘永远不会 import 它。
- **界面** — `src/telegram_bot.py`（原生 Bot API 长轮询）、`src/webapp.py`（Flask + 原生 JS + SQLite，见 `src/storage.py`）。
- **结构** — `src/`（9 个模块）· `tests/`（89 个测试）· `demo.py` · `.env.example` · `requirements.txt` / `requirements-live.txt`

</details>

---

> **想定制？** 按你的策略改鲸鱼提醒 —— 自定义阈值、Discord/X/Slack 推送、自动跟单规则、组合跟踪。
> DM [@saulgoodmanc99](https://t.me/saulgoodmanc99) —— Telegram 机器人定制 **$299 起**，USDT 结算。50% 定金，7 天 bug 保修。

MIT © Webhook Wizard
