"""Safety-rail tests for live trading. The SDK is ALWAYS faked here —
no test may touch the real network or sign anything real."""
import logging

import pytest

from src.live_trader import (LiveTrader, LiveTradingDisabled, NeedsConfirmation,
                             OrderTooLarge, SdkNotInstalled)
from tests.conftest import FAKE_KEY, FakeSdk, make_config


def live_trader(**over):
    cfg = make_config(live_trading=True, private_key=FAKE_KEY, **over)
    return LiveTrader(cfg, sdk=FakeSdk)


# -- gate -----------------------------------------------------------------
def test_place_refused_without_flag():
    t = LiveTrader(make_config(live_trading=False, private_key=FAKE_KEY),
                   sdk=FakeSdk)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    with pytest.raises(LiveTradingDisabled):
        t.place_order(p, confirmed=True)


def test_place_refused_without_key():
    t = LiveTrader(make_config(live_trading=True, private_key=""), sdk=FakeSdk)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    with pytest.raises(LiveTradingDisabled):
        t.place_order(p, confirmed=True)


def test_place_refused_with_malformed_key():
    t = LiveTrader(make_config(live_trading=True, private_key="0xbad"),
                   sdk=FakeSdk)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    with pytest.raises(LiveTradingDisabled):
        t.place_order(p, confirmed=True)


def test_enabled_property():
    assert live_trader().enabled
    assert not LiveTrader(make_config(), sdk=FakeSdk).enabled


# -- cap -------------------------------------------------------------------
def test_order_above_cap_rejected_before_signing():
    t = live_trader(max_order_usd=25.0)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 100)  # $100
    with pytest.raises(OrderTooLarge):
        t.place_order(p, confirmed=True)
    assert FakeSdk.last_client is None or not FakeSdk.last_client.orders


def test_order_at_cap_allowed():
    t = live_trader(max_order_usd=25.0)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 25)  # exactly $25
    # needs confirmation first, but cap itself must not reject
    with pytest.raises(NeedsConfirmation):
        t.place_order(p, confirmed=False)


# -- dry run / confirmation --------------------------------------------------
def test_preview_signs_nothing():
    t = live_trader()
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    assert p.usd_value == 10.0
    assert p.mode == "live"
    assert FakeSdk.last_client is None  # no client built, nothing signed


def test_unconfirmed_order_raises_with_preview():
    t = live_trader()
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    with pytest.raises(NeedsConfirmation) as exc:
        t.place_order(p, confirmed=False)
    assert exc.value.preview is p
    assert "NOT signed" in str(exc.value)


def test_confirmed_order_submits_once():
    t = live_trader()
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    resp = t.place_order(p, confirmed=True)
    assert resp["status"] == "accepted"
    client = FakeSdk.last_client
    assert len(client.orders) == 1
    o = client.orders[0]
    assert o["token_id"] == "tok" and o["price"] == 0.5
    assert o["side"] == "BUY"


def test_preview_validates_inputs():
    t = live_trader()
    with pytest.raises(ValueError):
        t.preview_order("tok", "M", "HOLD", "Yes", 0.5, 10)
    with pytest.raises(ValueError):
        t.preview_order("tok", "M", "BUY", "Yes", 1.5, 10)
    with pytest.raises(ValueError):
        t.preview_order("tok", "M", "BUY", "Yes", 0.5, -5)


# -- key hygiene ---------------------------------------------------------------
def test_key_never_in_logs(caplog):
    cfg = make_config(live_trading=True, private_key=FAKE_KEY)
    with caplog.at_level(logging.INFO):
        LiveTrader(cfg, sdk=FakeSdk)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in blob


def test_key_never_in_exceptions():
    t = live_trader()
    big = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 9999)
    with pytest.raises(OrderTooLarge) as exc:
        t.place_order(big, confirmed=True)
    assert FAKE_KEY not in str(exc.value)


def test_sdk_missing_gives_clear_error():
    t = LiveTrader(make_config(live_trading=True, private_key=FAKE_KEY),
                   sdk=None)
    # polymarket not installed in test env -> SdkNotInstalled on client build
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    import sys
    assert "polymarket" not in sys.modules  # sanity: really not installed
    with pytest.raises(SdkNotInstalled):
        t.place_order(p, confirmed=True)


def test_client_init_failure_sanitized():
    class BadSdk:
        OrderSide = FakeSdk.OrderSide

        class SecureClient:
            @classmethod
            def create(cls, private_key):
                raise RuntimeError(f"boom with key {private_key}")

    t = LiveTrader(make_config(live_trading=True, private_key=FAKE_KEY),
                   sdk=BadSdk)
    p = t.preview_order("tok", "M", "BUY", "Yes", 0.5, 10)
    with pytest.raises(LiveTradingDisabled) as exc:
        t.place_order(p, confirmed=True)
    assert FAKE_KEY not in str(exc.value)
