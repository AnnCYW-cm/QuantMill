# -*- coding: utf-8 -*-
"""
_util.py —— 数据层共享底件(无依赖,供 provider/sources/__init__ 复用)
=====================================================================
把原先散在 data/__init__.py 里的归一化 / 重试 / 代码转换 / 缓存判定抽出来,
让 provider.py、sources.py 能引用而不产生循环导入。行为与原实现逐字一致。
"""
from __future__ import annotations

import os

import pandas as pd

from quantmill import config

_DATA_DIR = config.DATA_DIR

# backtesting.py 要求的标准列 | standard columns required by backtesting.py
_STD_COLS = ["Open", "High", "Low", "Close", "Volume"]

# A股 / 港股(akshare)中文列名 -> 标准列名
_CN_RENAME = {"日期": "Date", "开盘": "Open", "最高": "High",
              "最低": "Low", "收盘": "Close", "成交量": "Volume"}


def _cache_path(symbol: str, market: str) -> str:
    safe = symbol.replace("/", "_").replace(".", "_")
    return os.path.join(_DATA_DIR, f"{market}_{safe}.csv")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """任意来源 -> 标准列 + 排序 DatetimeIndex + 去空。行为同原 data._normalize。"""
    df = df[_STD_COLS].copy()
    for c in _STD_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)
    return df


def _retry(fn, tries: int = 3):
    """不稳定联网调用重试几次(eastmoney 常抽风)。"""
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _cn_to_yahoo(symbol: str) -> str:
    """A股代码 -> yfinance:6开头=沪.SS,其余=深.SZ。"""
    return f"{symbol}.SS" if symbol.startswith("6") else f"{symbol}.SZ"


def _hk_to_yahoo(symbol: str) -> str:
    """港股代码 -> yfinance:akshare 用5位 00700,yahoo 用 0700.HK。"""
    digits = symbol.replace(".HK", "").lstrip("0") or "0"
    return f"{digits.zfill(4)}.HK"


def _cache_sufficient(cached_index, start_ts, end_ts):
    """缓存够不够:够早(覆盖历史)且够新(不过期)。返回 (early_ok, fresh_ok)。"""
    early_ok = cached_index[0] <= start_ts + pd.Timedelta(days=7)
    fresh_ok = cached_index[-1] >= end_ts - pd.Timedelta(days=5)
    return early_ok, fresh_ok
