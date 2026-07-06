# -*- coding: utf-8 -*-
"""
可插拔 DataProvider 测试 —— 离线,用假源焊死接口/契约/组合/换源。
不碰网络:所有源都是内存假实现或本地 parquet。
"""
import numpy as np
import pandas as pd
import pytest

from quantmill.data.provider import (CachingSource, ChainSource, Registry,
                                     assert_bar_contract,
                                     assert_fundamental_contract,
                                     assert_universe_contract)


# ---- 假源 ----------------------------------------------------------------
def _bars_df(n=5, base=10.0):
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({"Open": base, "High": base + 1, "Low": base - 1,
                         "Close": base + 0.5, "Volume": 100}, index=idx)


class FakeBars:
    name = "fake"
    def __init__(self, fail=False): self.fail = fail; self.calls = 0
    def markets(self): return {"cn"}
    def bars(self, symbol, market, start, end):
        self.calls += 1
        if self.fail:
            raise ValueError("假装挂了")
        return _bars_df()


# ---- 契约 ----------------------------------------------------------------
def test_bar_contract_ok():
    df = assert_bar_contract(FakeBars(), "X", "cn", "2023-01-01", "2023-02-01")
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_fundamental_contract_needs_available_date():
    class NoAvail:
        def fundamentals(self, *a):
            return pd.DataFrame({"pe": [10.0]}, index=pd.to_datetime(["2023-01-03"]))
    with pytest.raises(AssertionError):
        assert_fundamental_contract(NoAvail(), "X", "cn", "2023-01-01", "2023-02-01")


def test_fundamental_contract_rejects_future_available_date():
    """available_date 早于数据日 = 未来函数,必须被契约拦下。"""
    class FutureLeak:
        def fundamentals(self, *a):
            idx = pd.to_datetime(["2023-06-01"])
            return pd.DataFrame({"pe": [10.0], "available_date": pd.to_datetime(["2023-01-01"])}, index=idx)
    with pytest.raises(AssertionError):
        assert_fundamental_contract(FutureLeak(), "X", "cn", "2023-01-01", "2023-12-01")


def test_universe_contract_rejects_lookahead():
    """返回了 asof 之后才纳入的成分 = 前视偏差,必须被拦下。"""
    class Leaky:
        def universe(self, *a):
            return pd.DataFrame({"symbol": ["A"], "in_date": pd.to_datetime(["2024-01-01"]),
                                 "out_date": [pd.NaT]})
    with pytest.raises(AssertionError):
        assert_universe_contract(Leaky(), "cn", "000300", "2023-01-01")


# ---- ChainSource 回退 -----------------------------------------------------
def test_chain_falls_back_on_failure():
    bad, good = FakeBars(fail=True), FakeBars()
    chain = ChainSource([bad, good])
    df = chain.bars("X", "cn", "2023-01-01", "2023-02-01")
    assert len(df) == 5
    assert bad.calls == 1 and good.calls == 1        # 坏的试过、回退到好的


def test_chain_all_fail_raises():
    chain = ChainSource([FakeBars(fail=True), FakeBars(fail=True)])
    with pytest.raises(ValueError):
        chain.bars("X", "cn", "2023-01-01", "2023-02-01")


def test_chain_markets_union():
    class UsBars(FakeBars):
        def markets(self): return {"us"}
    assert ChainSource([FakeBars(), UsBars()]).markets() == {"cn", "us"}


# ---- CachingSource:第二次读缓存不再打源 ----------------------------------
def test_caching_source_hits_cache(tmp_path, monkeypatch):
    from quantmill.data import _util
    monkeypatch.setattr(_util, "_DATA_DIR", str(tmp_path))
    inner = FakeBars()
    cs = CachingSource(inner)
    a = cs.bars("X", "cn", "2023-01-02", "2023-01-06")
    b = cs.bars("X", "cn", "2023-01-02", "2023-01-06")
    assert inner.calls == 1                          # 第二次命中缓存,没再打源
    assert a.equals(b)


# ---- Registry 解析 + 环境变量换源 ----------------------------------------
def test_registry_get_set():
    r = Registry()
    src = FakeBars()
    r.set("bars", "cn", src)
    assert r.bars("cn") is src
    with pytest.raises(ValueError):
        r.bars("hk")


def test_env_swaps_source(monkeypatch):
    """QUANTMILL_BARS_CN 环境变量应能整源替换(这就是"换源")。"""
    monkeypatch.setenv("QUANTMILL_BARS_CN", "parquet")
    import importlib

    import quantmill.data as d
    importlib.reload(d)
    try:
        inner = d.REGISTRY.bars("cn").inner        # CachingSource.inner
        assert "parquet" in inner.name
    finally:
        monkeypatch.delenv("QUANTMILL_BARS_CN", raising=False)
        importlib.reload(d)


# ---- ParquetProvider:接自己的本地数据 -----------------------------------
def test_universe_hk_us_through_abstraction():
    """hk/us universe 现在也走 UniverseSource,返回统一 PIT 形状并过契约(离线)。"""
    import quantmill.data as d
    for m in ("hk", "us"):
        df = assert_universe_contract(d.REGISTRY.universe(m), m, "-", "2023-01-01")
        assert len(df) > 10 and {"symbol", "in_date", "out_date"} <= set(df.columns)
    assert d.universe_df("us", asof="2023-01-01")["symbol"].str.len().gt(0).all()


def test_parquet_provider_reads_local(tmp_path):
    pytest.importorskip("pyarrow")               # 自备数据模板用 parquet,需 pyarrow(可选依赖)
    from quantmill.data.sources import ParquetProvider
    p = ParquetProvider(root=str(tmp_path))
    df = _bars_df()
    fp = tmp_path / "cn_600000.parquet"
    df.to_parquet(fp)
    out = p.bars("600000", "cn", "2023-01-01", "2023-02-01")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(out) == 5
