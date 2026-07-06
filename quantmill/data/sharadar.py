# -*- coding: utf-8 -*-
"""
sharadar.py —— SharadarProvider(经 Nasdaq Data Link)| PIT 干净的美股数据
=====================================================================
为什么值得接:Sharadar 是零售最划算的【PIT 干净、survivorship-free】美股源,
正好填平台两个天花板:
  · SF1 表有 `datekey`(SEC 备案日)= 天然的 available_date → 严格 PIT 基本面
  · SP500 表有历史成分(含被踢出的死票)→ 真实 universe,无幸存者偏差

实现全部四接口:bars(SEP)/ fundamentals(SF1)/ universe(SP500)/ quotes(SEP 末行)。
骨架:填好 API key(见 _load_key)+ `pip install -e ".[sharadar]"` 即可跑;
不联网时用 monkeypatch _get_table 可离线测映射(见 tests/test_sharadar.py)。

⚠️ 这是模板,作者未跑通真实账号(无 key);列名按 Sharadar 官方 schema 映射,
   接上后若某列名有出入,改 _MAP_* 即可。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from quantmill.data._util import _normalize


def _load_key() -> str | None:
    """API key:环境变量优先,其次 ~/quant/.sharadar 文件(与 .alpaca 同风格,gitignore)。"""
    for var in ("NASDAQ_DATA_LINK_API_KEY", "QUANTMILL_SHARADAR_KEY", "QUANDL_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    path = os.path.expanduser("~/quant/.sharadar")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.split("=")[-1].strip()
    return None


class SharadarProvider:
    name = "sharadar"

    def __init__(self, key: str | None = None):
        self._key = key                      # 延迟到真正取数才校验,构造不报错(便于注册)

    def markets(self) -> set:
        return {"us"}

    # ---- 底层:一次拉一张 Sharadar 表(懒加载 nasdaqdatalink;测试可 monkeypatch)----
    def _get_table(self, name: str, **filters) -> pd.DataFrame:
        try:
            import nasdaqdatalink
        except ImportError as e:
            raise ImportError('SharadarProvider 需要 `pip install -e ".[sharadar]"`') from e
        key = self._key or _load_key()
        if not key:
            raise RuntimeError("缺少 Nasdaq Data Link API key(设 NASDAQ_DATA_LINK_API_KEY 或写 ~/quant/.sharadar)")
        nasdaqdatalink.ApiConfig.api_key = key
        return nasdaqdatalink.get_table(name, paginate=True, **filters)

    # ---- bars:SEP 表(用 closeadj 复权,O/H/L 按同因子缩放,与 yfinance auto_adjust 口径一致)----
    def bars(self, symbol, market, start, end):
        raw = self._get_table("SHARADAR/SEP", ticker=symbol,
                               date={"gte": start, "lte": end})
        if raw is None or raw.empty:
            raise ValueError(f"Sharadar SEP 无数据:{symbol}")
        df = raw.set_index(pd.to_datetime(raw["date"])).sort_index()
        adj = (df["closeadj"] / df["close"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        out = pd.DataFrame({
            "Open": df["open"] * adj, "High": df["high"] * adj,
            "Low": df["low"] * adj, "Close": df["closeadj"], "Volume": df["volume"],
        })
        return _normalize(out)

    # ---- fundamentals:SF1(dimension=ARQ 为"as-reported 季度",datekey=备案日=available_date)----
    _MAP_SF1 = {"pe": "pe", "pb": "pb", "marketcap": "mktcap"}   # Sharadar 列 -> 平台列

    def fundamentals(self, symbol, market, start, end):
        raw = self._get_table("SHARADAR/SF1", ticker=symbol, dimension="ARQ",
                               calendardate={"gte": start, "lte": end})
        if raw is None or raw.empty:
            raise ValueError(f"Sharadar SF1 无数据:{symbol}")
        cols = {k: v for k, v in self._MAP_SF1.items() if k in raw.columns}
        out = raw[list(cols)].rename(columns=cols).copy()
        out.index = pd.to_datetime(raw["reportperiod"])          # 数据对应期末日
        out["available_date"] = pd.to_datetime(raw["datekey"].values)  # SEC 备案日 = 可知日(PIT)
        return out.sort_index()

    # ---- universe:SP500 表(含 added/removed 动作)-> [symbol,in_date,out_date],无幸存者偏差 ----
    def universe(self, market, index, asof):
        raw = self._get_table("SHARADAR/SP500")
        if raw is None or raw.empty:
            raise ValueError("Sharadar SP500 无数据")
        ev = raw.assign(date=pd.to_datetime(raw["date"])).sort_values("date")
        opens, rows = {}, []
        for _, r in ev.iterrows():
            t, act, d = r["ticker"], str(r["action"]).lower(), r["date"]
            if act == "added":
                opens[t] = d
            elif act == "removed":
                rows.append({"symbol": t, "in_date": opens.pop(t, pd.NaT), "out_date": d})
        for t, d in opens.items():                               # 仍在册的 → out_date=NaT
            rows.append({"symbol": t, "in_date": d, "out_date": pd.NaT})
        u = pd.DataFrame(rows, columns=["symbol", "in_date", "out_date"])
        return u.loc[pd.to_datetime(u["in_date"]) <= pd.Timestamp(asof)].reset_index(drop=True)

    # ---- quotes:SEP 每只票末行收盘 ----
    def quotes(self, symbols, market):
        out = {}
        for s in symbols:
            try:
                df = self._get_table("SHARADAR/SEP", ticker=s)
                out[s] = float(df.sort_values("date")["closeadj"].iloc[-1])
            except Exception:  # noqa: BLE001
                pass
        return pd.DataFrame({"price": pd.Series(out)})
