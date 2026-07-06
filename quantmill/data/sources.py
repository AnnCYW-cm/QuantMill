# -*- coding: utf-8 -*-
"""
sources.py —— 具体数据源实现(把原散落逻辑搬进 provider)
=====================================================================
YFinanceProvider   bars(us/cn/hk,自动转代码)+ quotes
AkshareProvider    bars(cn/hk,qfq)+ fundamentals(百度估值,PIT)+ universe(成分股)
StaticUniverse     hk/us 静态蓝筹池(带 in_date 让 PIT 契约通过)
ParquetProvider    参考实现:接你自己的本地/付费数据(data/custom/<market>_<sym>.parquet)
所有 bars 返回前都过 _normalize;回退由 provider.ChainSource 负责,这里各源失败就抛。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from quantmill import config
from quantmill.data._util import (_cn_to_yahoo, _CN_RENAME, _hk_to_yahoo,
                                  _normalize, _retry)


# ============================================================ yfinance ========
class YFinanceProvider:
    name = "yfinance"

    def markets(self) -> set:
        return {"us", "cn", "hk"}

    def _ysym(self, symbol: str, market: str) -> str:
        if market == "cn":
            return _cn_to_yahoo(symbol)
        if market == "hk":
            return _hk_to_yahoo(symbol)
        return symbol

    def bars(self, symbol, market, start, end):
        import yfinance as yf
        ysym = self._ysym(symbol, market)
        df = yf.download(ysym, start=start, end=end, auto_adjust=True, progress=False)
        if df is None or df.empty:
            raise ValueError(f"yfinance 没返回数据:{ysym}(代码对吗?)")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return _normalize(df)

    def quotes(self, symbols, market):
        import yfinance as yf
        out = {}
        for s in symbols:
            try:
                px = yf.Ticker(self._ysym(s, market)).fast_info["last_price"]
                out[s] = float(px)
            except Exception:  # noqa: BLE001
                pass
        return pd.DataFrame({"price": pd.Series(out)})


# ============================================================= akshare ========
class AkshareProvider:
    name = "akshare"

    def markets(self) -> set:
        return {"cn", "hk"}

    # ---- bars(cn/hk,前复权 qfq;失败抛,由 Chain 回退 yfinance)----
    def bars(self, symbol, market, start, end):
        import akshare as ak
        if market not in ("cn", "hk"):
            raise ValueError(f"akshare bars 不支持 {market}")
        fn = ak.stock_zh_a_hist if market == "cn" else ak.stock_hk_hist
        df = _retry(lambda: fn(symbol=symbol, period="daily",
                               start_date=start.replace("-", ""),
                               end_date=end.replace("-", ""), adjust="qfq"))
        if df is None or df.empty:
            raise ValueError("akshare 返回空")
        df = df.rename(columns=_CN_RENAME)
        df["Date"] = pd.to_datetime(df["Date"])
        return _normalize(df.set_index("Date"))

    # ---- fundamentals(百度 PE-TTM/PB/总市值;价格衍生→当日可知,available_date=当日)----
    def fundamentals(self, symbol, market, start, end):
        import akshare as ak
        if market not in ("cn", "hk"):
            raise ValueError(f"akshare fundamentals 不支持 {market}")
        fn = ak.stock_zh_valuation_baidu if market == "cn" else ak.stock_hk_valuation_baidu
        out = {}
        for ind, col in [("市盈率(TTM)", "pe"), ("市净率", "pb"), ("总市值", "mktcap")]:
            try:
                d = fn(symbol=symbol, indicator=ind, period="近三年")
                out[col] = pd.Series(d["value"].to_numpy(), index=pd.to_datetime(d["date"]))
            except Exception:  # noqa: BLE001
                pass
        if not out:
            raise ValueError("百度估值三项全空")
        v = pd.DataFrame(out).sort_index()
        v = v.loc[pd.Timestamp(start):pd.Timestamp(end)] if len(v) else v
        v["available_date"] = v.index            # 估值比率由当日价格算得 → 当日即可知(PIT)
        return v

    # ---- universe(成分股 + 纳入日期;out_date 缺→NaT,即"只知现有成分")----
    def universe(self, market, index, asof):
        import akshare as ak
        if market != "cn":
            raise ValueError("akshare universe 目前只支持 cn 指数")
        d = ak.index_stock_cons(symbol=index)
        d["纳入日期"] = pd.to_datetime(d["纳入日期"])
        out = pd.DataFrame({
            "symbol": d["品种代码"].astype(str).str.zfill(6),
            "in_date": d["纳入日期"],
            "out_date": pd.NaT,
        })
        return out.loc[out["in_date"] <= pd.Timestamp(asof)].reset_index(drop=True)


# ======================================================== 静态兜底池 ==========
# 复用 cross.universe 里维护的 hk/us 蓝筹清单,避免两处重复。
class StaticUniverseProvider:
    name = "static"

    def __init__(self, market: str, symbols: list, in_date: str = "2000-01-01"):
        self.market = market
        self.symbols = symbols
        self.in_date = pd.Timestamp(in_date)

    def universe(self, market, index, asof):
        return pd.DataFrame({"symbol": self.symbols, "in_date": self.in_date,
                             "out_date": pd.NaT})


# ================================================= 参考:接你自己的数据 ========
class ParquetProvider:
    """把你的本地/付费日线放到 data/custom/<market>_<symbol>.parquet,即可当数据源。
    列需含 Open/High/Low/Close/Volume,索引为日期。这是"接机构/付费数据"的模板。"""
    name = "parquet"

    def __init__(self, root: str | None = None):
        self.root = root or os.path.join(config.DATA_DIR, "custom")

    def markets(self) -> set:
        return {"us", "cn", "hk"}

    def _p(self, symbol, market):
        safe = symbol.replace("/", "_").replace(".", "_")
        return os.path.join(self.root, f"{market}_{safe}.parquet")

    def bars(self, symbol, market, start, end):
        p = self._p(symbol, market)
        if not os.path.exists(p):
            raise FileNotFoundError(f"无自备数据:{p}")
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return _normalize(df).loc[pd.Timestamp(start):pd.Timestamp(end)]
