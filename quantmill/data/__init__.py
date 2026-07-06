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

logger = logging.getLogger(__name__)

# 向后兼容:这些底件已搬到 _util,原路径仍可 import(news/market 等依赖它们)。
# Backward compat: these helpers moved to _util; old import paths still work.
from quantmill.data._util import (  # noqa: E402,F401
    _cache_path, _cache_sufficient, _cn_to_yahoo, _CN_RENAME, _DATA_DIR,
    _hk_to_yahoo, _normalize, _retry, _STD_COLS)
from quantmill.data.provider import (  # noqa: E402
    CachingSource, ChainSource, Registry)
from quantmill.data.sources import (  # noqa: E402
    AkshareProvider, ParquetProvider, StaticUniverseProvider, YFinanceProvider)

# ----------------------------------------------------------------------
# 组装默认数据源注册表 | assemble the default provider registry
# ----------------------------------------------------------------------
# 命名的 provider 实例池:环境变量可按名字换源(见 _env_chain)。
_PROVIDERS = {
    "yfinance": YFinanceProvider(),
    "akshare": AkshareProvider(),
    "parquet": ParquetProvider(),
}


def _env_chain(cap: str, market: str, default_names: list):
    """按 QUANTMILL_<CAP>_<MARKET> 环境变量选源(逗号分隔的 provider 名),否则用默认。
    例:QUANTMILL_BARS_CN=parquet,yfinance —— 优先自备数据,回退 yfinance。这就是"换源"。"""
    env = os.environ.get(f"QUANTMILL_{cap.upper()}_{market.upper()}")
    names = [n.strip() for n in env.split(",")] if env else list(default_names)
    srcs = [_PROVIDERS[n] for n in names if n in _PROVIDERS]
    if not srcs:
        srcs = [_PROVIDERS[default_names[0]]]
    return ChainSource(srcs) if len(srcs) > 1 else srcs[0]


def _build_registry() -> Registry:
    r = Registry()
    # bars:cn/hk 先 akshare(qfq)后 yfinance 回退,us 用 yfinance;都套 CSV 缓存(沿用现有缓存)
    for m in ("cn", "hk"):
        r.set("bars", m, CachingSource(_env_chain("bars", m, ["akshare", "yfinance"])))
    r.set("bars", "us", CachingSource(_env_chain("bars", "us", ["yfinance"])))
    # fundamentals:cn/hk 百度估值(akshare);us 无免费历史估值 → 不注册(调用方自行退化)
    for m in ("cn", "hk"):
        r.set("fundamentals", m, _env_chain("fundamentals", m, ["akshare"]))
    # universe:cn 用真实成分股(带纳入日期,PIT);hk/us 暂留 cross.universe 的静态清单(不在此注册)
    r.set("universe", "cn", _env_chain("universe", "cn", ["akshare"]))
    # quotes:三市场先用 yfinance(美股可另配 alpaca 实时,见 data/live.py)
    for m in ("cn", "hk", "us"):
        r.set("quotes", m, _PROVIDERS["yfinance"])
    return r


REGISTRY = _build_registry()


# ----------------------------------------------------------------------
# 对外统一入口(薄门面,底层走 REGISTRY;调用点无需改)| public facades
# ----------------------------------------------------------------------
def get_ohlcv(
    symbol: str,
    market: str = "us",
    start: str = config.START,
    end: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """抓任意市场日线,返回标准化 OHLCV(列 [Open,High,Low,Close,Volume],DatetimeIndex)。
    Fetch daily bars for any market; standardized OHLCV. 现在底层走可插拔 REGISTRY,行为不变。

    use_cache=False 时绕过缓存直连数据源(取最新)。
    """
    market = market.lower()
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    src = REGISTRY.bars(market)                       # CachingSource(链)
    if not use_cache and isinstance(src, CachingSource):
        src = src.inner                               # 绕过缓存,直连源
        df = _normalize(src.bars(symbol, market, start, end))
        return df.loc[pd.Timestamp(start):pd.Timestamp(end)]
    return src.bars(symbol, market, start, end)


def fundamentals(symbol: str, market: str = "cn",
                 start: str = config.START, end: str | None = None):
    """基本面(PE/PB/市值 等)+ available_date(PIT)。us 无免费源 → 抛/None 由调用方兜底。"""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    return REGISTRY.fundamentals(market).fundamentals(symbol, market, start, end)


def universe_df(market: str = "cn", index: str = "000300", asof: str = "2023-01-01"):
    """成分股面板:cols=[symbol,in_date,out_date],只含 asof 前已纳入(无前视/幸存偏差)。"""
    return REGISTRY.universe(market).universe(market, index, asof)


def quotes(symbols, market: str = "us"):
    """最新报价:index=symbol,含 price 列。"""
    return REGISTRY.quotes(market).quotes(list(symbols), market)


if __name__ == "__main__":
    # 自测:三个市场各抓一个,确认统一格式 | Self-test: one symbol per market
    for sym, mkt in [("AAPL", "us"), ("000001", "cn"), ("00700", "hk")]:
        print("=" * 60)
        try:
            d = get_ohlcv(sym, mkt, start="2023-01-01", end="2024-01-01")
            print(d.tail(3))
        except Exception as e:
            print(f"[失败] {mkt}:{sym} -> {e}")
