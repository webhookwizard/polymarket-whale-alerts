"""Synthetic trade feed for demo and tests. Zero network, zero keys.

Replays realistic whale + retail trades so `python3 demo.py` works
out of the box and the test-suite never touches the network.
"""
from __future__ import annotations

import random
import time

from .models import Trade

# A small pool of plausible markets (titles/slugs only — no real data).
MOCK_MARKETS = [
    ("Will Bitcoin hit $150k by New Year?", "bitcoin-150k-new-year"),
    ("Will the Fed cut rates in December?", "fed-december-rate-cut"),
    ("NBA: Will the Celtics win the championship?", "celtics-championship"),
    ("Will SpaceX launch Starship Flight 9 in Q4?", "starship-flight-9-q4"),
    ("US election: Republican popular vote win?", "us-popular-vote-winner"),
    ("Will ETH ETF see $1B inflows this month?", "eth-etf-1b-inflows"),
]

MOCK_TRADERS = ["DeepPocket", "0xWhale", "SilentAccumulator", "degen_trader",
                "PaperHands", "ColdWallet_88", "anon"]


class MockFeed:
    """Generates an endless stream of synthetic trades."""

    def __init__(self, seed: int | None = 42, whale_probability: float = 0.25) -> None:
        self.rng = random.Random(seed)
        self.whale_probability = whale_probability
        self._counter = 0

    def next_trade(self) -> Trade:
        self._counter += 1
        title, slug = self.rng.choice(MOCK_MARKETS)
        is_whale = self.rng.random() < self.whale_probability
        if is_whale:
            usd = self.rng.uniform(12_000, 250_000)
        else:
            usd = self.rng.uniform(5, 900)
        price = round(self.rng.uniform(0.08, 0.92), 3)
        size_shares = round(usd / price, 2)
        outcome = self.rng.choice(["Yes", "Yes", "No"])
        return Trade(
            tx_hash=f"0xmock{self._counter:08d}{self.rng.randrange(10**8):08d}",
            market_title=title,
            market_slug=slug,
            condition_id=f"0xmockcond{self.rng.randrange(10**6):06d}",
            token_id=f"mocktoken{self.rng.randrange(10**12)}",
            side=self.rng.choice(["BUY", "BUY", "SELL"]),
            outcome=outcome,
            size_shares=size_shares,
            price=price,
            timestamp=int(time.time()) - self.rng.randrange(0, 120),
            trader=self.rng.choice(MOCK_TRADERS),
        )

    def batch(self, n: int) -> list[Trade]:
        return [self.next_trade() for _ in range(n)]
