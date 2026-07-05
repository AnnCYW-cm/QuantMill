# -*- coding: utf-8 -*-
"""
cb_ipo.py —— 可转债打新 诚实验证 | convertible-bond new-issue, honestly
=====================================================================
营销口径:"2025 首日均涨 20%+、几乎零破发!"
诚实口径:扣掉【中签率】(单账户已 <0.05%),每账户每年期望只有几百元;
          且首日翻卖 ≠ 持有到期(信用违约退市是独立尾部风险)。

抓取(akshare,你自己机器上跑;本沙箱 eastmoney 不通)与分析(纯函数、可离线测)分离。
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

from quantmill import config

logger = logging.getLogger(__name__)
_CACHE = os.path.join(config.DATA_DIR, "cb_first_days.csv")


def fetch_cb_universe() -> pd.DataFrame | None:
    """全部可转债一览(代码/简称/申购日/上市日/正股/发行规模)。失败返回 None。"""
    try:
        import akshare as ak
        return ak.bond_zh_cov()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[cb] 拉取可转债一览失败(本沙箱 eastmoney 常不通,你机器上应正常):{type(e).__name__}")
        return None


def _first_day_return(code: str) -> float | None:
    """单只可转债的首日收益率(首日收盘/发行价100 - 1)。"""
    try:
        import akshare as ak
        h = ak.bond_zh_hs_cov_daily(symbol=code)   # 二级市场日线
        if h is None or len(h) == 0:
            return None
        return float(h.iloc[0]["close"]) / 100.0 - 1.0
    except Exception:  # noqa: BLE001
        return None


def fetch_cb_first_days(limit: int | None = None, refresh: bool = False) -> pd.DataFrame | None:
    """组装 [代码, 简称, 上市年, 首日收益率] 数据集,缓存到 data/cb_first_days.csv。
    首次要逐只拉首日行情(较慢),之后走缓存。"""
    if not refresh and os.path.exists(_CACHE):
        return pd.read_csv(_CACHE, dtype={"code": str})
    uni = fetch_cb_universe()
    if uni is None or len(uni) == 0:
        return None
    code_col = next((c for c in uni.columns if "代码" in c and "正股" not in c), uni.columns[0])
    name_col = next((c for c in uni.columns if "简称" in c and "正股" not in c), None)
    list_col = next((c for c in uni.columns if "上市" in c), None)
    rows = []
    codes = uni[code_col].astype(str).tolist()
    if limit:
        codes = codes[:limit]
    for i, code in enumerate(codes):
        r = _first_day_return(code)
        if r is None:
            continue
        yr = None
        if list_col is not None:
            try:
                yr = pd.to_datetime(uni.iloc[i][list_col]).year
            except Exception:
                pass
        rows.append({"code": code,
                     "name": uni.iloc[i][name_col] if name_col else "",
                     "list_year": yr, "first_day_return": r})
        if (i + 1) % 50 == 0:
            logger.info(f"[cb] ...{i+1}/{len(codes)}")
    df = pd.DataFrame(rows).dropna(subset=["first_day_return"])
    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_csv(_CACHE, index=False)
    return df


def load_sample_cb() -> pd.DataFrame:
    """随包合成样本(388只×2020-2025,分布贴近真实),离线演示/测试用。"""
    from importlib.resources import files
    with files("quantmill.niche").joinpath("sample", "cb_sample.csv").open("rb") as f:
        return pd.read_csv(f, dtype={"code": str})


def analyze_cb_ipo(df: pd.DataFrame, win_rate: float = 0.00003,
                   max_hands: int = 1000, face_per_hand: float = 1000.0) -> dict:
    """诚实经济学:首日收益分布 + 破发率(按年)+ 扣中签率后每账户期望。

    ⚠️ 结果对 win_rate 极度敏感——默认按 2024 实测每账户约 200 元/年反推(集思录口径),
       你务必用自己账户的真实中签率覆盖(--win-rate)。
    win_rate    单账户每手中签率(默认 0.003%)
    max_hands   顶格申购手数(默认1000手)
    face_per_hand 1手面值(10张×100=1000元)
    """
    r = df["first_day_return"].astype(float)
    n = len(r)
    exp_hands = win_rate * max_hands                       # 每只新债期望中签手数/账户
    ev_per_cb = exp_hands * r.mean() * face_per_hand       # 每只新债期望收益(元/账户)
    out = {
        "n_bonds": n,
        "break_rate": round(float((r < 0).mean()) * 100, 1),       # 破发率%
        "mean_first_day": round(float(r.mean()) * 100, 2),          # 首日均值%
        "median_first_day": round(float(r.median()) * 100, 2),
        "pct_gain_10": round(float((r >= 0.10).mean()) * 100, 1),   # 涨超10%占比
        "pct_gain_20": round(float((r >= 0.20).mean()) * 100, 1),
        "exp_hands_per_cb": round(exp_hands, 3),
        "ev_yuan_per_cb": round(ev_per_cb, 1),                      # 每只新债期望收益(元/账户)
        "ev_yuan_per_year": round(ev_per_cb * (n / max(1, _years(df))), 0),  # 年化期望(元/账户)
    }
    if "list_year" in df.columns and df["list_year"].notna().any():
        by = df.dropna(subset=["list_year"]).groupby("list_year")["first_day_return"]
        out["by_year"] = {int(y): {"n": int(g.size),
                                   "break%": round(float((g < 0).mean()) * 100, 1),
                                   "mean%": round(float(g.mean()) * 100, 1)}
                          for y, g in by}
    return out


def _years(df: pd.DataFrame) -> int:
    if "list_year" in df.columns and df["list_year"].notna().any():
        ys = df["list_year"].dropna()
        return max(1, int(ys.max() - ys.min() + 1))
    return 1
