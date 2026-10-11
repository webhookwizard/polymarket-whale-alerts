import os

import pytest

from src.config import Config, looks_like_private_key
from tests.conftest import FAKE_KEY, make_config


def test_key_format_valid():
    assert looks_like_private_key(FAKE_KEY)
    assert looks_like_private_key("0x" + "F" * 64)


def test_key_format_invalid():
    assert not looks_like_private_key("")
    assert not looks_like_private_key("0x1234")
    assert not looks_like_private_key("not-a-key")
    assert not looks_like_private_key("0x" + "g" * 64)  # non-hex
    assert not looks_like_private_key("0x" + "a" * 63)  # too short


def test_gate_closed_by_default():
    c = make_config()
    ok, reason = c.live_gate()
    assert not ok
    assert "paper" in reason.lower()


def test_gate_needs_both_flag_and_key():
    c = make_config(live_trading=True, private_key="")
    ok, _ = c.live_gate()
    assert not ok
    c = make_config(live_trading=False, private_key=FAKE_KEY)
    ok, _ = c.live_gate()
    assert not ok


def test_gate_rejects_malformed_key():
    c = make_config(live_trading=True, private_key="0x1234")
    ok, reason = c.live_gate()
    assert not ok
    assert "malformed" in reason.lower()
    assert "0x1234" not in reason  # never echo the key


def test_gate_opens_with_flag_and_good_key():
    c = make_config(live_trading=True, private_key=FAKE_KEY)
    ok, _ = c.live_gate()
    assert ok
    assert c.live_enabled


def test_fingerprint_redacts_key():
    c = make_config(private_key=FAKE_KEY)
    fp = c.key_fingerprint()
    assert FAKE_KEY not in fp
    assert len(fp) < 20


def test_gate_reason_never_contains_key():
    c = make_config(live_trading=True, private_key="0xbad")
    _, reason = c.live_gate()
    assert "0xbad" not in reason


def test_from_env_reads_vars(monkeypatch):
    monkeypatch.setenv("DEFAULT_MIN_USD", "5000")
    monkeypatch.setenv("POLY_MAX_ORDER_USD", "10")
    c = Config.from_env()
    assert c.default_min_usd == 5000
    assert c.max_order_usd == 10
