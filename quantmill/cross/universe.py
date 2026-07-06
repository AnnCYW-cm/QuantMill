"""
universe.py —— 股票池:沪深300成分股 | investable universe: CSI 300
=====================================================================
一个真实、可交易的股票池是横截面选股的前提(不能只在几只自选股上排名)。
成分股会变,这里先用「当前成分股」并缓存;⚠️这带有幸存者偏差,回测会略偏乐观,
真正 PIT 需要历史成分股快照(收费),我们诚实标注、以后再补。
A real investable universe is the premise of cross-sectional selection.
We use *current* constituents (cached); this carries survivorship bias.
"""
from __future__ import annotations

import json
import logging
import os

from quantmill import config

logger = logging.getLogger(__name__)

_CACHE = os.path.join(config.DATA_DIR, "csi300_cons.json")

# 静态清单单一来源在 data.sources(hk/us 蓝筹 + cn 兜底);这里 import 复用,不再重复维护。
from quantmill.data.sources import CN_FALLBACK as _FALLBACK  # noqa: E402


def csi300(refresh: bool = False) -> list[str]:
    """沪深300成分股代码(6位字符串)。缓存到 data/,失败回退静态池。
    CSI 300 constituent tickers (6-digit); cached, static fallback on failure."""
    if not refresh and os.path.exists(_CACHE):
        try:
            return json.load(open(_CACHE))["symbols"]
        except Exception:
            pass
    try:
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol="000300")
        syms = df["成分券代码"].astype(str).str.zfill(6).tolist()
        os.makedirs(config.DATA_DIR, exist_ok=True)
        json.dump({"symbols": syms, "asof": str(df["日期"].iloc[0])},
                  open(_CACHE, "w"), ensure_ascii=False)
        return syms
    except Exception as e:
        logger.warning(f"[universe] 成分股拉取失败,用静态兜底池:{type(e).__name__}")
        return _FALLBACK


def sample(n: int = 12, refresh: bool = False) -> list[str]:
    """取前 n 只做快速开发/教学(可复现,不随机)。| first n names for fast dev/teaching."""
    return csi300(refresh)[:n]


def csi300_pit(asof: str = "2023-01-01", refresh: bool = False) -> list[str]:
    """PIT(point-in-time)池:纳入 CSI300 早于 asof 的现有成分股。
    去掉「2023后才因为涨得好被纳入」的前视偏差(这是幸存者偏差里可免费修的一半)。
    ⚠️仍缺「起点在、后来被踢出」的股票(需付费PIT数据),故只是部分修复。"""
    cache = os.path.join(config.DATA_DIR, f"csi300_pit_{asof}.json")
    if not refresh and os.path.exists(cache):
        try:
            return json.load(open(cache))["symbols"]
        except Exception:
            pass
    try:
        import akshare as ak
        import pandas as pd
        d = ak.index_stock_cons(symbol="000300")
        d["纳入日期"] = pd.to_datetime(d["纳入日期"])
        syms = d.loc[d["纳入日期"] < asof, "品种代码"].astype(str).str.zfill(6).tolist()
        os.makedirs(config.DATA_DIR, exist_ok=True)
        json.dump({"symbols": syms, "asof": asof}, open(cache, "w"), ensure_ascii=False)
        return syms
    except Exception as e:
        logger.warning(f"[universe] PIT 成分股拉取失败:{type(e).__name__}")
        return []


# hk/us 蓝筹清单单一来源在 data.sources(带幸存者偏差,已诚实标注)
from quantmill.data.sources import HK_BLUE as _HK, US_BLUE as _US  # noqa: E402


def universe(market: str = "cn", n: int | None = None, refresh: bool = False) -> list[str]:
    """按市场取股票池:cn=沪深300全池;hk/us=蓝筹起步池。n 截断前 n 只。
    Universe by market: cn=full CSI300, hk/us=blue-chip starter lists."""
    if market == "cn":
        u = csi300(refresh)
    elif market == "hk":
        u = list(_HK)
    elif market == "us":
        u = list(_US)
    else:
        raise ValueError(f"未知市场 {market}(cn/hk/us)")
    return u[:n] if n else u
