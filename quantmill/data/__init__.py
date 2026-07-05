# -*- coding: utf-8 -*-
"""
data.py —— 统一多市场数据层
data.py —— Unified multi-market data layer
============================
一个函数 get_ohlcv(symbol, market) 吃三个市场,底层自动分发数据源:
A single function get_ohlcv(symbol, market) handles three markets, automatically
dispatching to the right data source underneath:

    美股/ETF  ->  yfinance   例:  get_ohlcv("AAPL", "us")
    US stocks/ETF  ->  yfinance   e.g.  get_ohlcv("AAPL", "us")
    A股       ->  akshare    例:  get_ohlcv("000001", "cn")
    China A-shares ->  akshare   e.g.  get_ohlcv("000001", "cn")
    港股      ->  akshare    例:  get_ohlcv("00700", "hk")
    HK stocks     ->  akshare    e.g.  get_ohlcv("00700", "hk")

难点:三个数据源返回的格式完全不同(A股/港股是中文列名),这里把它们
统一成 backtesting.py 认的标准格式:
Difficulty: the three data sources return completely different formats (A-shares/HK
use Chinese column names). Here they are unified into the standard format that
backtesting.py expects:
    - 列名固定为 Open / High / Low / Close / Volume(首字母大写,缺一不可)
    - Fixed column names Open / High / Low / Close / Volume (capitalized, none may be missing)
    - 索引是 DatetimeIndex(时间从早到晚排序)
    - The index is a DatetimeIndex (sorted from earliest to latest)

所有下载结果都缓存到 data/ 目录,避免重复联网、加速反复实验。
All download results are cached to the data/ directory to avoid repeated network
calls and speed up repeated experiments.
"""

from __future__ import annotations

import logging

import os
from datetime import datetime

import pandas as pd

from quantmill import config

# data/ 缓存目录(相对本文件定位,和当前工作目录无关) | data/ cache directory (located relative to this file, independent of the current working directory)
_DATA_DIR = config.DATA_DIR

# backtesting.py 要求的标准列 | Standard columns required by backtesting.py
_STD_COLS = ["Open", "High", "Low", "Close", "Volume"]

# A股 / 港股(akshare)中文列名 -> 标准列名 | A-shares / HK (akshare) Chinese column names -> standard column names
_CN_RENAME = {
    "日期": "Date",
    "开盘": "Open",
    "最高": "High",
    "最低": "Low",
    "收盘": "Close",
    "成交量": "Volume",
}


logger = logging.getLogger(__name__)

def _cache_path(symbol: str, market: str) -> str:
    safe = symbol.replace("/", "_").replace(".", "_")
    return os.path.join(_DATA_DIR, f"{market}_{safe}.csv")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """把任意来源的行情整理成标准格式:标准列 + 排序的 DatetimeIndex + 去空。
    Normalize market data from any source into the standard format: standard columns +
    sorted DatetimeIndex + dropped nulls.
    """
    df = df[_STD_COLS].copy()
    # 强制转成数字,脏数据变 NaN | Force numeric conversion; dirty data becomes NaN
    for c in _STD_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~df.index.duplicated(keep="last")]  # 去掉重复日期 | Drop duplicate dates
    df = df.sort_index()                          # 时间从早到晚 | Sort from earliest to latest
    df = df.dropna(subset=["Open", "High", "Low", "Close"])  # 价格不能缺 | Prices must not be missing
    df["Volume"] = df["Volume"].fillna(0)
    return df


# ----------------------------------------------------------------------
# 各市场的抓取实现 | Per-market fetch implementations
# ----------------------------------------------------------------------
def _fetch_us(symbol: str, start: str, end: str) -> pd.DataFrame:
    """美股/ETF:yfinance。auto_adjust=True 用复权价(把分红拆股的跳空抹平)。
    US stocks/ETF: yfinance. auto_adjust=True uses adjusted prices (smooths out gaps
    from dividends and stock splits).
    """
    import yfinance as yf

    df = yf.download(symbol, start=start, end=end, auto_adjust=True,
                     progress=False)
    if df is None or df.empty:
        raise ValueError(f"yfinance 没返回数据:{symbol}(代码对吗?)")
    # 新版 yfinance 列是 MultiIndex (字段, 代码),拍平取第一层 | Newer yfinance returns MultiIndex columns (field, symbol); flatten and take the first level
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    return df


def _retry(fn, tries: int = 3):
    """把不稳定的联网调用重试几次(eastmoney 数据源常抽风)。
    Retry an unstable network call a few times (the eastmoney data source often flakes out).
    """
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _cn_to_yahoo(symbol: str) -> str:
    """A股代码转 yfinance 格式:6开头=沪市.SS,其余=深市.SZ。
    Convert an A-share code to yfinance format: starts with 6 = Shanghai .SS, otherwise = Shenzhen .SZ.
    """
    return f"{symbol}.SS" if symbol.startswith("6") else f"{symbol}.SZ"


def _fetch_cn(symbol: str, start: str, end: str) -> pd.DataFrame:
    """A股:akshare(qfq前复权)优先,连不上自动回退 yfinance。
    A-shares: prefer akshare (qfq forward-adjusted); fall back to yfinance automatically if unreachable.
    """
    import akshare as ak

    try:
        df = _retry(lambda: ak.stock_zh_a_hist(
            symbol=symbol, period="daily",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust="qfq",
        ))
        if df is None or df.empty:
            raise ValueError("akshare 返回空")
        df = df.rename(columns=_CN_RENAME)
        df["Date"] = pd.to_datetime(df["Date"])
        return df.set_index("Date")
    except Exception as e:
        yahoo_sym = _cn_to_yahoo(symbol)
        logger.warning(f"[A股] akshare 失败({type(e).__name__}),回退 yfinance:{yahoo_sym}")
        return _fetch_us(yahoo_sym, start, end)


def _hk_to_yahoo(symbol: str) -> str:
    """港股代码转 yfinance 格式:akshare 用5位 00700,yahoo 用 0700.HK。
    Convert an HK code to yfinance format: akshare uses 5 digits like 00700, yahoo uses 0700.HK.
    """
    digits = symbol.replace(".HK", "").lstrip("0") or "0"
    return f"{digits.zfill(4)}.HK"


def _fetch_hk(symbol: str, start: str, end: str) -> pd.DataFrame:
    """港股:akshare 优先,连不上自动回退 yfinance。代码用5位,如腾讯 00700。
    HK stocks: prefer akshare; fall back to yfinance automatically if unreachable. Use 5-digit codes, e.g. Tencent 00700.
    """
    import akshare as ak

    try:
        df = _retry(lambda: ak.stock_hk_hist(
            symbol=symbol, period="daily",
            start_date=start.replace("-", ""), end_date=end.replace("-", ""),
            adjust="qfq",
        ))
        if df is None or df.empty:
            raise ValueError("akshare 返回空")
        df = df.rename(columns=_CN_RENAME)
        df["Date"] = pd.to_datetime(df["Date"])
        return df.set_index("Date")
    except Exception as e:
        # akshare(eastmoney)连不上就回退 yahoo,走的是另一套服务器 | If akshare (eastmoney) is unreachable, fall back to yahoo, which uses a different set of servers
        yahoo_sym = _hk_to_yahoo(symbol)
        logger.warning(f"[港股] akshare 失败({type(e).__name__}),回退 yfinance:{yahoo_sym}")
        return _fetch_us(yahoo_sym, start, end)


_FETCHERS = {"us": _fetch_us, "cn": _fetch_cn, "hk": _fetch_hk}


def _cache_sufficient(cached_index, start_ts, end_ts):
    """判断缓存够不够用:够早(覆盖历史)且够新(不过期)。返回 (early_ok, fresh_ok)。
    Is the cache good enough: early enough (covers history) and fresh enough (not stale)?
    Returns (early_ok, fresh_ok). 允许几天误差应对周末/假日。| A few days' slack for weekends/holidays."""
    early_ok = cached_index[0] <= start_ts + pd.Timedelta(days=7)
    fresh_ok = cached_index[-1] >= end_ts - pd.Timedelta(days=5)
    return early_ok, fresh_ok


# ----------------------------------------------------------------------
# 对外统一入口 | Unified public entry point
# ----------------------------------------------------------------------
def get_ohlcv(
    symbol: str,
    market: str = "us",
    start: str = config.START,
    end: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    抓取任意市场的日线行情,返回标准化 OHLCV。
    Fetch daily bars for any market and return standardized OHLCV.

    参数:
    Parameters:
        symbol : 代码。美股 "AAPL";A股 "000001";港股 "00700"
        symbol : code. US "AAPL"; A-share "000001"; HK "00700"
        market : "us" | "cn" | "hk"
        start / end : 日期 "YYYY-MM-DD"。end 默认今天
        start / end : dates "YYYY-MM-DD". end defaults to today
        use_cache : True 时优先读本地缓存,没有再联网并缓存
        use_cache : when True, read the local cache first; if absent, fetch online and cache it

    返回:
    Returns:
        DataFrame,列 = [Open, High, Low, Close, Volume],索引 = DatetimeIndex
        DataFrame, columns = [Open, High, Low, Close, Volume], index = DatetimeIndex
    """
    market = market.lower()
    if market not in _FETCHERS:
        raise ValueError(f"不支持的市场:{market},可选 {list(_FETCHERS)}")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(_DATA_DIR, exist_ok=True)
    cache = _cache_path(symbol, market)

    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    if use_cache and os.path.exists(cache):
        cached = _normalize(pd.read_csv(cache, index_col=0, parse_dates=True))
        # 缓存要满足两头:① 最早日期够早(<= start,覆盖历史);② 最新日期够新
        # (>= end 附近,别拿过期数据当"今日")。允许几天误差(周末/假日非交易日)。
        # 任一不满足就重新下载。
        # The cache must satisfy both ends: (1) early enough (<= start, covers history);
        # (2) fresh enough (near end, so we don't treat stale data as "today"). Allow a few
        # days of slack (weekends/holidays are non-trading). If either fails, re-download.
        early_ok, fresh_ok = _cache_sufficient(cached.index, start_ts, end_ts)
        if early_ok and fresh_ok:
            sub = cached.loc[start_ts:end_ts]
            logger.info(f"[缓存] {market}:{symbol}  {len(sub)} 根K线  "
                  f"{sub.index[0].date()} ~ {sub.index[-1].date()}")
            return sub
        reason = "历史不够早" if not early_ok else f"数据过期(止于 {cached.index[-1].date()})"
        logger.info(f"[缓存刷新] {market}:{symbol} {reason},重新下载")

    logger.info(f"[下载] {market}:{symbol} ...")
    raw = _FETCHERS[market](symbol, start, end)
    df = _normalize(raw)
    df.to_csv(cache)               # 缓存存下载到的全量 | Cache the full downloaded range
    df = df.loc[start_ts:end_ts]   # 返回请求区间 | Return only the requested range
    logger.info(f"[完成] {len(df)} 根K线  {df.index[0].date()} ~ {df.index[-1].date()}  "
                f"已缓存 -> {os.path.relpath(cache)}")
    return df


if __name__ == "__main__":
    # 自测:三个市场各抓一个,确认统一格式 | Self-test: fetch one symbol from each of the three markets to confirm the unified format
    for sym, mkt in [("AAPL", "us"), ("000001", "cn"), ("00700", "hk")]:
        print("=" * 60)
        try:
            d = get_ohlcv(sym, mkt, start="2023-01-01", end="2024-01-01")
            print(d.tail(3))
        except Exception as e:
            print(f"[失败] {mkt}:{sym} -> {e}")
