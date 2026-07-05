# -*- coding: utf-8 -*-
"""
etf_arb.py —— ETF 折溢价套利 诚实验证 | ETF premium/discount arbitrage, honestly
=====================================================================
机制真实:溢价时(价>净值)买一篮子股票→一级申购→二级卖 ETF;折价反之。
诚实提醒:最小申赎单位常达几十万~上百万(门槛)、停牌成分需现金替代、
          价差常在往返成本之内(可套利空间薄)、容量有限。
本工具做【当前横截面监控】:此刻有多少 ETF 的折溢价 > 成本(真机会数)。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def fetch_etf_premium() -> pd.DataFrame | None:
    """当前全市场 ETF 现价 + 折溢价率。失败返回 None(本沙箱 eastmoney 常不通)。
    返回列尽量规整为:code / name / price / premium(小数,正=溢价)。"""
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[etf] 拉取 ETF 现价失败(你机器上应正常):{type(e).__name__}")
        return None
    return _normalize(df)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    cols = df.columns
    code = next((c for c in cols if c in ("代码", "基金代码", "symbol")), cols[0])
    name = next((c for c in cols if "名称" in c or "简称" in c), None)
    prem = next((c for c in cols if "折价" in c or "溢价" in c), None)
    out = pd.DataFrame({"code": df[code].astype(str)})
    out["name"] = df[name] if name else ""
    if prem is not None:                                    # 直接有折溢价率(通常是百分数)
        out["premium"] = pd.to_numeric(df[prem], errors="coerce") / 100.0
    else:                                                   # 否则用 现价 vs IOPV 现算
        price = next((c for c in cols if c in ("最新价", "price")), None)
        iopv = next((c for c in cols if "IOPV" in c.upper()), None)
        if price and iopv:
            p = pd.to_numeric(df[price], errors="coerce")
            v = pd.to_numeric(df[iopv], errors="coerce")
            out["premium"] = p / v - 1.0
        else:
            out["premium"] = np.nan
    return out.dropna(subset=["premium"])


def analyze_etf_premium(df: pd.DataFrame, cost: float = 0.002) -> dict:
    """诚实监控:扣往返成本 cost 后,当前有多少 ETF 折溢价真的够套利。

    cost 往返成本(佣金+冲击+一二级摩擦),默认 0.2%。
    """
    p = df["premium"].astype(float)
    n = len(p)
    edge = p.abs() - cost                                   # 扣成本后的净空间
    exploit = df[edge > 0].assign(net=edge[edge > 0]).sort_values("net", ascending=False)
    return {
        "n_etf": n,
        "mean_abs_premium": round(float(p.abs().mean()) * 100, 3),      # 平均|折溢价|%
        "pct_over_cost": round(float((edge > 0).mean()) * 100, 1),      # 超成本的比例%
        "n_exploitable": int((edge > 0).sum()),                        # 够套利的只数
        "median_abs_premium": round(float(p.abs().median()) * 100, 3),
        "top": [{"code": r.code, "name": str(r.name)[:12],
                 "premium%": round(r.premium * 100, 2), "net%": round(r.net * 100, 2)}
                for r in exploit.head(10).itertuples()],
    }
