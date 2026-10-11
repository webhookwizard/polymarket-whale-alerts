from src.mock_feed import MockFeed


def test_batch_size():
    assert len(MockFeed(seed=1).batch(10)) == 10


def test_trades_have_required_fields():
    t = MockFeed(seed=2).next_trade()
    assert t.tx_hash.startswith("0xmock")
    assert t.market_title and t.market_slug
    assert 0 < t.price < 1
    assert t.usd_value > 0
    assert t.side in ("BUY", "SELL")


def test_whale_probability_produces_whales():
    feed = MockFeed(seed=3, whale_probability=1.0)
    whales = [t for t in feed.batch(20) if t.usd_value >= 10_000]
    assert len(whales) == 20


def test_no_whales_when_probability_zero():
    feed = MockFeed(seed=4, whale_probability=0.0)
    whales = [t for t in feed.batch(20) if t.usd_value >= 10_000]
    assert not whales


def test_tx_hashes_unique():
    feed = MockFeed(seed=5)
    hashes = [t.tx_hash for t in feed.batch(50)]
    assert len(set(hashes)) == 50
