# -*- coding: utf-8 -*-
"""
SharadarProvider 映射测试 —— 离线,用假表(monkeypatch _get_table)验证:
Sharadar 官方 schema → 平台契约(bars 标准列 / 基本面 available_date=备案日 / universe 无幸存者)。
不联网、不需 nasdaq-data-link 包、不需 key。
"""
import numpy as np
import pandas as pd

from quantmill.data.provider import (assert_bar_contract,
                                     assert_fundamental_contract,
                                     assert_universe_contract)
from quantmill.data.sharadar import SharadarProvider, _load_key


def _fake_sep():
    d = pd.date_range("2023-01-02", periods=4, freq="B")
    return pd.DataFrame({
        "ticker": "AAPL", "date": d,
        "open": [10, 11, 12, 13], "high": [11, 12, 13, 14], "low": [9, 10, 11, 12],
        "close": [10, 11, 12, 13], "closeadj": [20, 22, 24, 26],  # 复权因子=2,验证 O/H/L 缩放
        "volume": [100, 100, 100, 100],
    })


def _fake_sf1():
    # 数据期末 3/31,但 5/15 才备案(datekey)→ available_date 必须是 5/15,不是 3/31
    return pd.DataFrame({
        "ticker": "AAPL", "dimension": "ARQ",
        "reportperiod": pd.to_datetime(["2023-03-31"]),
        "datekey": pd.to_datetime(["2023-05-15"]),
        "calendardate": pd.to_datetime(["2023-03-31"]),
        "pe": [25.0], "pb": [5.0], "marketcap": [2.5e12],
    })


def _fake_sp500():
    return pd.DataFrame({
        "date": pd.to_datetime(["2015-01-01", "2015-01-01", "2020-06-01", "2024-01-01"]),
        "action": ["added", "added", "removed", "added"],
        "ticker": ["AAPL", "XYZ", "XYZ", "NEWCO"],   # XYZ 被踢出(死票)、NEWCO 2024才进
    })


def _patch(monkeypatch, mapping):
    def fake(self, name, **kw):
        return mapping[name.split("/")[-1]]
    monkeypatch.setattr(SharadarProvider, "_get_table", fake)


def test_bars_maps_and_adjusts(monkeypatch):
    _patch(monkeypatch, {"SEP": _fake_sep()})
    df = assert_bar_contract(SharadarProvider(), "AAPL", "us", "2023-01-01", "2023-02-01")
    assert df["Close"].iloc[0] == 20                 # closeadj
    assert df["Open"].iloc[0] == 20                  # open(10)×adj(2)=20,O/H/L 同因子缩放


def test_fundamentals_available_date_is_filing_date(monkeypatch):
    """核心:available_date = datekey(备案日 5/15),不是数据期末(3/31)。"""
    _patch(monkeypatch, {"SF1": _fake_sf1()})
    df = assert_fundamental_contract(SharadarProvider(), "AAPL", "us", "2023-01-01", "2023-12-01")
    assert "mktcap" in df.columns and "pe" in df.columns   # marketcap 已改名 mktcap
    assert pd.Timestamp(df["available_date"].iloc[0]) == pd.Timestamp("2023-05-15")
    assert df.index[0] == pd.Timestamp("2023-03-31")       # 数据日=期末


def test_universe_survivorship_free(monkeypatch):
    """XYZ 2020 被踢出必须仍出现(死票),NEWCO 2024 才进则在 2023 asof 被排除。"""
    _patch(monkeypatch, {"SP500": _fake_sp500()})
    df = assert_universe_contract(SharadarProvider(), "us", "SP500", "2023-01-01")
    syms = set(df["symbol"])
    assert "XYZ" in syms                              # 被踢出的死票没被幸存者偏差抹掉
    assert "NEWCO" not in syms                        # 2024 才纳入,2023 看不到(无前视)
    xyz = df.loc[df["symbol"] == "XYZ"].iloc[0]
    assert pd.Timestamp(xyz["out_date"]) == pd.Timestamp("2020-06-01")


def test_registered_and_swappable(monkeypatch):
    """已注册进 _PROVIDERS,可被 QUANTMILL_BARS_US=sharadar 换源。"""
    monkeypatch.setenv("QUANTMILL_BARS_US", "sharadar,yfinance")
    import importlib

    import quantmill.data as d
    importlib.reload(d)
    try:
        assert "sharadar" in d._PROVIDERS
        assert "sharadar" in d.REGISTRY.bars("us").inner.name   # 链里排第一
    finally:
        monkeypatch.delenv("QUANTMILL_BARS_US", raising=False)
        importlib.reload(d)


def test_us_fundamentals_registered_and_valuation_degrades(monkeypatch, tmp_path):
    """门已打开:us 基本面注册到 sharadar;无 key/包时 _valuation('X','us') 优雅退化为 None。"""
    from quantmill import config
    from quantmill.cross.panel import _valuation
    import quantmill.data as d
    assert d.REGISTRY.fundamentals("us")                 # us 现在有源(sharadar)
    for v in ("NASDAQ_DATA_LINK_API_KEY", "QUANTMILL_SHARADAR_KEY", "QUANDL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))    # 干净缓存目录
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "none"))
    assert _valuation("AAPL", "us") is None              # 无 key → None,不抛,退化纯量价


def test_valuation_us_uses_source_when_available(monkeypatch, tmp_path):
    """配了 us 基本面源时,_valuation('X','us') 真的取到基本面(用假 Sharadar 表验证)。"""
    from quantmill import config
    from quantmill.cross.panel import _valuation
    from quantmill.data.sharadar import SharadarProvider
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "none"))
    monkeypatch.setattr(SharadarProvider, "_get_table", lambda self, name, **k: _fake_sf1())
    v = _valuation("AAPL", "us")
    assert v is not None and "pe" in v.columns and "available_date" in v.columns


def test_load_key_missing_returns_none(monkeypatch, tmp_path):
    for v in ("NASDAQ_DATA_LINK_API_KEY", "QUANTMILL_SHARADAR_KEY", "QUANDL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("os.path.expanduser", lambda p: str(tmp_path / "nope"))
    assert _load_key() is None
