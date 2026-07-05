# -*- coding: utf-8 -*-
"""
panel.py —— 横截面面板 | cross-sectional panel builder
=====================================================================
把「每只票各自一张时序表」堆成一张 MultiIndex(date, symbol) 的**面板**:
    每一行 = 某天某只股票的 [量价因子 + 基本面因子 + 未来收益标签]

这是横截面建模的地基——模型将学「同一天里,哪只票比哪只强」。
Stack per-symbol time series into one (date, symbol) panel; each row is
one stock on one day: [technical factors + fundamental factors + label].

基本面因子(来自百度估值,每日、point-in-time 干净):
    ey   = 1/PE      盈利收益率(价值)| earnings yield  (value)
    bp   = 1/PB      账面市值比        | book-to-price   (value)
    size = ln(市值)   规模             | size (log market cap)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from quantmill import config
from quantmill.data import get_ohlcv
from quantmill.factor.library import FEATURE_COLS, compute_factors

VALUE_COLS = ["ey", "bp", "size"]   # 基本面因子列 | fundamental factor columns


def _val_cache(symbol: str, market: str) -> str:
    # A股沿用旧文件名(向后兼容已缓存的300只);其它市场加市场前缀
    name = f"val_{symbol}.csv" if market == "cn" else f"val_{market}_{symbol}.csv"
    return os.path.join(config.DATA_DIR, name)


def _valuation(symbol: str, market: str = "cn", period: str = "近三年") -> pd.DataFrame | None:
    """百度源估值:PE-TTM / PB / 总市值 -> DataFrame(index=date)。缓存到 data/。
    A股/港股有免费每日历史(baidu);美股无免费历史估值,返回 None(退化为纯量价)。
    Daily valuation via Baidu (CN & HK only); US has no free history -> None."""
    if market not in ("cn", "hk"):
        return None
    cache = _val_cache(symbol, market)
    if os.path.exists(cache):
        try:
            return pd.read_csv(cache, index_col=0, parse_dates=True)
        except Exception:
            pass
    try:
        import akshare as ak
        fn = ak.stock_zh_valuation_baidu if market == "cn" else ak.stock_hk_valuation_baidu
        out = {}
        for ind, col in [("市盈率(TTM)", "pe"), ("市净率", "pb"), ("总市值", "mktcap")]:
            try:                                   # 逐列容错:某一项挂了不影响其它
                d = fn(symbol=symbol, indicator=ind, period=period)
                out[col] = pd.Series(d["value"].to_numpy(), index=pd.to_datetime(d["date"]))
            except Exception:
                pass
        if not out:
            return None
        v = pd.DataFrame(out).sort_index()
        os.makedirs(config.DATA_DIR, exist_ok=True)
        v.to_csv(cache)
        return v
    except Exception:
        return None


def build_panel(symbols, market: str = "cn", start=None, end=None, horizon: int = 20,
                with_value: bool = True, min_rows: int = 80,
                verbose: bool = True) -> pd.DataFrame:
    """构建横截面面板。| Build the cross-sectional panel.

    market: cn/hk/us(cn/hk 带基本面因子,us 退化为纯量价)。
    label 「fwd」= 未来 horizon 天的收益率(横截面里做相对排名用)。
    """
    start = start or config.START
    frames, ok, skip = [], 0, 0
    for sym in symbols:
        try:
            df = get_ohlcv(sym, market, start=start, end=end)
        except Exception:
            skip += 1
            continue
        if df is None or len(df) < min_rows:
            skip += 1
            continue
        feats = compute_factors(df)                                   # 量价因子
        feats["fwd"] = df["Close"].shift(-horizon) / df["Close"] - 1  # 标签:未来收益
        if with_value:
            v = _valuation(sym, market)
            if v is not None:
                v = v.reindex(df.index).ffill()          # 对齐交易日+前向填充(当天可知,PIT)
                if "pe" in v:                             # 逐列容错:缺哪列就不加哪个因子
                    feats["ey"] = 1.0 / v["pe"].replace(0, np.nan)
                if "pb" in v:
                    feats["bp"] = 1.0 / v["pb"].replace(0, np.nan)
                if "mktcap" in v:
                    feats["size"] = np.log(v["mktcap"].replace(0, np.nan))
        feats = feats.reset_index()
        feats.columns = ["date"] + list(feats.columns[1:])            # 首列强制命名 date
        feats["symbol"] = sym
        frames.append(feats)
        ok += 1
        if verbose:
            print(f"  ✓ {sym}  ({len(df)} 天)")
    if not frames:
        raise RuntimeError("面板为空:所有标的都拉取失败(检查网络/代码)。")
    if verbose:
        print(f"[panel] 成功 {ok} 只 / 跳过 {skip} 只")
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.set_index(["date", "symbol"]).sort_index()
    return panel


def factor_columns(panel: pd.DataFrame, with_value: bool = True) -> list[str]:
    """面板里可用的因子列(量价 + 可选基本面)。| available factor columns."""
    cols = [c for c in FEATURE_COLS if c in panel.columns]
    if with_value:
        cols += [c for c in VALUE_COLS if c in panel.columns]
    return cols
