# -*- coding: utf-8 -*-
"""
test_live.py —— 实时行情源(Alpaca)容错 | real-time quote source fallback
=====================================================================
没 key 时必须静默返回空(让调用方安全退回 yfinance),绝不抛异常。
"""

from quantmill.data import live


def _clear_keys(monkeypatch):
    for k in ("ALPACA_API_KEY_ID", "APCA_API_KEY_ID",
              "ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_no_keys_not_available(monkeypatch):
    _clear_keys(monkeypatch)
    assert live.alpaca_available() is False


def test_no_keys_returns_empty_not_raise(monkeypatch):
    _clear_keys(monkeypatch)
    assert live.alpaca_last_prices(["AAPL", "MSFT"]) == {}


def test_empty_symbols_returns_empty(monkeypatch):
    # 即便有 key,空标的也直接返回空,不发请求
    monkeypatch.setenv("ALPACA_API_KEY_ID", "x")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "y")
    assert live.alpaca_last_prices([]) == {}
