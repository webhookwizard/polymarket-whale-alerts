from unittest.mock import MagicMock

import pytest
import requests

from src.polymarket_client import PolymarketClient, PolymarketError


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError("bad")
    else:
        r.raise_for_status.return_value = None
    return r


def test_get_trades_parses():
    s = MagicMock()
    s.get.return_value = _resp([{
        "transactionHash": "0xh", "title": "Q", "slug": "q",
        "size": "200", "price": "0.5", "side": "BUY", "outcome": "Yes",
        "timestamp": "1", "asset": "tok"}])
    c = PolymarketClient(session=s)
    trades = c.get_trades(limit=5)
    assert len(trades) == 1
    assert trades[0].usd_value == 100.0


def test_get_trades_skips_bad_rows():
    s = MagicMock()
    s.get.return_value = _resp(["not-a-dict", {"transactionHash": "0xok",
        "size": "10", "price": "0.5"}])
    c = PolymarketClient(session=s)
    trades = c.get_trades()
    assert len(trades) == 1
    assert trades[0].tx_hash == "0xok"


def test_retry_then_success():
    s = MagicMock()
    s.get.side_effect = [requests.ConnectionError("down"),
                         _resp([])]
    c = PolymarketClient(session=s, max_retries=2)
    assert c.get_trades() == []
    assert s.get.call_count == 2


def test_retry_exhausted_raises():
    s = MagicMock()
    s.get.side_effect = requests.Timeout("slow")
    c = PolymarketClient(session=s, max_retries=2)
    with pytest.raises(PolymarketError):
        c.get_trades()


def test_search_markets():
    s = MagicMock()
    s.get.return_value = _resp({"events": [{"id": 1}]})
    c = PolymarketClient(session=s)
    assert c.search_markets("btc") == [{"id": 1}]


def test_get_market_price_none_on_failure():
    s = MagicMock()
    s.get.side_effect = requests.ConnectionError("x")
    c = PolymarketClient(session=s, max_retries=1)
    assert c.get_market_price("tok") is None
