# -*- coding: utf-8 -*-
"""
provider.py —— 可插拔数据源:四个小接口 + 注册 + 组合(Chain/Caching)+ 契约
=====================================================================
四个单一职责接口(纯 pandas 返回,契约由 assert_*_contract 测试焊死):
    BarSource         日线行情 bars()
    FundamentalSource 基本面 fundamentals()  —— 每行带 available_date(PIT)
    UniverseSource    成分股 universe()       —— 带 in_date/out_date(无幸存者偏差)
    QuoteSource       最新报价 quotes()
provider 按需实现能实现的接口;ChainSource 做回退,CachingSource 做缓存,
Registry 按 (市场, 能力) 解析 —— 换源只改注册/环境变量,15 处调用点无感。
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

import pandas as pd

from quantmill.data._util import (_cache_path, _cache_sufficient, _normalize)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- 接口 --------
@runtime_checkable
class BarSource(Protocol):
    name: str
    def markets(self) -> set: ...
    def bars(self, symbol: str, market: str, start: str, end: str) -> pd.DataFrame: ...
    #   -> index=DatetimeIndex(升序);cols=[Open,High,Low,Close,Volume];复权口径 provider 自负


@runtime_checkable
class FundamentalSource(Protocol):
    name: str
    def fundamentals(self, symbol: str, market: str, start: str, end: str) -> pd.DataFrame: ...
    #   -> index=DatetimeIndex(数据对应日);必含列 available_date(该值【公开可用】之日,含披露滞后)


@runtime_checkable
class UniverseSource(Protocol):
    name: str
    def universe(self, market: str, index: str, asof: str) -> pd.DataFrame: ...
    #   -> cols=[symbol, in_date, out_date];只返回 asof 之前已纳入的成分(out_date 可为 NaT=仍在)


@runtime_checkable
class QuoteSource(Protocol):
    name: str
    def quotes(self, symbols: list, market: str) -> pd.DataFrame: ...
    #   -> index=symbol;至少含 price 列(实时/延迟由 provider 自报)


# ------------------------------------------------------------- 组合器 --------
class ChainSource:
    """按顺序尝试多个源,某个抛异常就回退下一个(替掉焊死的 akshare→yfinance)。
    对四种能力都透明代理:只调用内部源里【支持该能力】的,全失败则抛最后一个异常。"""

    def __init__(self, sources: list, name: str | None = None):
        self.sources = sources
        self.name = name or "chain(" + ",".join(getattr(s, "name", "?") for s in sources) + ")"

    def markets(self) -> set:
        out: set = set()
        for s in self.sources:
            if hasattr(s, "markets"):
                out |= set(s.markets())
        return out

    def _try(self, method: str, *args):
        last = None
        supported = [s for s in self.sources if hasattr(s, method)]
        if not supported:
            raise NotImplementedError(f"链中无源支持 {method}")
        for s in supported:
            try:
                return getattr(s, method)(*args)
            except Exception as e:  # noqa: BLE001
                last = e
                logger.warning(f"[链] {getattr(s,'name','?')}.{method} 失败({type(e).__name__}),回退")
        raise last

    def bars(self, symbol, market, start, end):
        return self._try("bars", symbol, market, start, end)

    def fundamentals(self, symbol, market, start, end):
        return self._try("fundamentals", symbol, market, start, end)

    def universe(self, market, index, asof):
        return self._try("universe", market, index, asof)

    def quotes(self, symbols, market):
        return self._try("quotes", symbols, market)


class CachingSource:
    """包一个 BarSource,加本地缓存(逐字复刻原 get_ohlcv 的早/新判定与区间返回)。
    默认 CSV store(沿用现有 data/<market>_<symbol>.csv 缓存,零失效);store 可换 parquet。"""

    def __init__(self, inner, store=None):
        self.inner = inner
        self.name = f"cached({getattr(inner,'name','?')})"
        self.store = store or _CsvBarStore()

    def markets(self) -> set:
        return set(self.inner.markets()) if hasattr(self.inner, "markets") else set()

    def bars(self, symbol, market, start, end):
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        cached = self.store.read(symbol, market)
        if cached is not None and len(cached):
            early_ok, fresh_ok = _cache_sufficient(cached.index, start_ts, end_ts)
            if early_ok and fresh_ok:
                sub = cached.loc[start_ts:end_ts]
                logger.info(f"[缓存] {market}:{symbol}  {len(sub)} 根K线")
                return sub
            reason = "历史不够早" if not early_ok else f"过期(止于 {cached.index[-1].date()})"
            logger.info(f"[缓存刷新] {market}:{symbol} {reason}")
        logger.info(f"[下载] {market}:{symbol} ...")
        df = _normalize(self.inner.bars(symbol, market, start, end))
        self.store.write(symbol, market, df)
        return df.loc[start_ts:end_ts]


class _CsvBarStore:
    """原样沿用现有 CSV 缓存(data/<market>_<symbol>.csv)。"""

    def read(self, symbol, market):
        p = _cache_path(symbol, market)
        if not os.path.exists(p):
            return None
        return _normalize(pd.read_csv(p, index_col=0, parse_dates=True))

    def write(self, symbol, market, df):
        os.makedirs(os.path.dirname(_cache_path(symbol, market)), exist_ok=True)
        df.to_csv(_cache_path(symbol, market))


class _ParquetBarStore:
    """可选:parquet 缓存(data/bars/<market>_<symbol>.parquet)。换 store 即换格式。"""

    def _p(self, symbol, market):
        from quantmill.data._util import _DATA_DIR
        safe = symbol.replace("/", "_").replace(".", "_")
        return os.path.join(_DATA_DIR, "bars", f"{market}_{safe}.parquet")

    def read(self, symbol, market):
        p = self._p(symbol, market)
        return _normalize(pd.read_parquet(p)) if os.path.exists(p) else None

    def write(self, symbol, market, df):
        p = self._p(symbol, market)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        df.to_parquet(p)


# -------------------------------------------------------------- 注册表 --------
class Registry:
    """按 (市场, 能力) 解析已组装好的源。默认由 data/__init__ 构建,可被环境变量覆盖。"""

    def __init__(self):
        self._by_cap: dict = {"bars": {}, "fundamentals": {}, "universe": {}, "quotes": {}}

    def set(self, cap: str, market: str, source):
        self._by_cap[cap][market.lower()] = source

    def get(self, cap: str, market: str):
        m = market.lower()
        table = self._by_cap[cap]
        if m not in table:
            raise ValueError(f"市场 {m} 没有 {cap} 数据源;已注册:{list(table)}")
        return table[m]

    def bars(self, market):
        return self.get("bars", market)

    def fundamentals(self, market):
        return self.get("fundamentals", market)

    def universe(self, market):
        return self.get("universe", market)

    def quotes(self, market):
        return self.get("quotes", market)


# --------------------------------------------------------- 契约(可测)--------
def assert_bar_contract(src, symbol, market, start, end):
    df = src.bars(symbol, market, start, end)
    assert list(df.columns[:5]) == ["Open", "High", "Low", "Close", "Volume"], "bars 列不标准"
    assert isinstance(df.index, pd.DatetimeIndex), "bars 索引必须 DatetimeIndex"
    assert df.index.is_monotonic_increasing, "bars 必须按时间升序"
    return df


def assert_fundamental_contract(src, symbol, market, start, end):
    df = src.fundamentals(symbol, market, start, end)
    assert "available_date" in df.columns, "基本面必须带 available_date(PIT 契约)"
    assert isinstance(df.index, pd.DatetimeIndex), "基本面索引必须 DatetimeIndex"
    av = pd.to_datetime(df["available_date"])
    assert (av >= df.index).all(), "available_date 不得早于数据日(否则=未来函数)"
    return df


def assert_universe_contract(src, market, index, asof):
    df = src.universe(market, index, asof)
    for col in ("symbol", "in_date", "out_date"):
        assert col in df.columns, f"universe 必须含 {col}"
    assert (pd.to_datetime(df["in_date"]) <= pd.Timestamp(asof)).all(), \
        "universe 只能返回 asof 之前已纳入的(无幸存者/前视偏差)"
    return df
