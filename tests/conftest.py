"""Shared fixtures. No test in this suite touches the real network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import Config
from src.live_trader import LiveTrader
from src.mock_feed import MockFeed
from src.models import Trade, WatcherConfig
from src.paper_trader import PaperTrader
from src.storage import Storage
from src.trade_router import TradeRouter
from src.watcher import WhaleWatcher

FAKE_KEY = "0x" + "a" * 64


def make_trade(usd=50_000, price=0.65, side="BUY", outcome="Yes",
               slug="test-market", tx="0xabc123"):
    size = usd / price
    return Trade(tx_hash=tx, market_title="Test Market", market_slug=slug,
                 token_id="tok123", side=side, outcome=outcome,
                 size_shares=size, price=price, timestamp=1_700_000_000,
                 trader="tester")


def make_config(**overrides):
    c = Config.__new__(Config)
    # bypass env: set sane defaults directly
    c.poll_interval_sec = 15
    c.default_min_usd = 10_000
    c.default_prob_min = 0.05
    c.default_prob_max = 0.95
    c.tg_token = ""
    c.tg_default_chat = ""
    c.web_host = "127.0.0.1"
    c.web_port = 5000
    c.db_path = ":memory:"
    c.live_trading = False
    c.private_key = ""
    c.max_order_usd = 25.0
    c.chain_id = 137
    c.wallet_override = ""
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


@pytest.fixture
def storage():
    s = Storage(":memory:")
    yield s
    s.close()


@pytest.fixture
def paper(storage):
    return PaperTrader(storage, price_fn=lambda token_id: 0.70)


@pytest.fixture
def live_paper():
    """LiveTrader that must stay in paper mode (no key)."""
    return LiveTrader(make_config())


@pytest.fixture
def router(storage, paper, live_paper):
    return TradeRouter(storage, paper, live_paper)


# -- fake Polymarket SDK -------------------------------------------------
class FakeOrderSide:
    BUY = "BUY"
    SELL = "SELL"


class FakeSdkClient:
    def __init__(self):
        self.orders = []

    def place_limit_order(self, *, token_id, price, size, side):
        rec = {"token_id": token_id, "price": price,
               "size": size, "side": side}
        self.orders.append(rec)
        return {"id": "fake-order-1", "status": "accepted", **rec}


class FakeSdk:
    OrderSide = FakeOrderSide

    last_client = None

    class SecureClient:
        @classmethod
        def create(cls, private_key):
            c = FakeSdkClient()
            FakeSdk.last_client = c
            return c
