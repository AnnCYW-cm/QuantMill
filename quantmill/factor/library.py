# -*- coding: utf-8 -*-
"""
library.py —— 因子库(用表达式定义)| Factor library (defined as expressions)
=============================================================================
每个因子就是一行表达式(见 expr.py 的算子)。改/加因子只改这里,不动代码逻辑。
Each factor is a one-line expression. Add/edit factors here, not in code.

分类:动量 / 均线偏离 / 波动率 / 量能 / 价格位置 / 形态 / 价量关系。
所有因子严格向后(不偷看未来)——由 tests/test_factor.py 锁定。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantmill.factor.expr import evaluate

# name -> 表达式 | name -> expression
FACTORS: dict[str, str] = {
    # --- 动量 Momentum:过去 N 天涨了多少 ---
    "ret_1d": "Returns(Close,1)",
    "ret_5d": "Returns(Close,5)",
    "ret_10d": "Returns(Close,10)",
    "ret_20d": "Returns(Close,20)",
    "ret_60d": "Returns(Close,60)",
    "mom_accel": "Returns(Close,5) - Returns(Close,20)",       # 动量加速度 | momentum acceleration
    "intraday_ret": "Close/Open - 1",                          # 日内收益 | intraday return
    "gap": "Open/Ref(Close,1) - 1",                            # 隔夜跳空 | overnight gap

    # --- 均线偏离 SMA deviation ---
    "close_sma5": "Close/Mean(Close,5) - 1",
    "close_sma10": "Close/Mean(Close,10) - 1",
    "close_sma20": "Close/Mean(Close,20) - 1",
    "close_sma60": "Close/Mean(Close,60) - 1",
    "sma5_sma20": "Mean(Close,5)/Mean(Close,20) - 1",          # 快慢均线(金叉连续版)
    "close_ema20": "Close/Ema(Close,20) - 1",                  # 相对 EMA20 偏离
    "macd_norm": "(Ema(Close,12) - Ema(Close,26))/Close",      # 归一化 MACD

    # --- 动量指标 RSI ---
    "rsi_6": "Rsi(Close,6)",
    "rsi_14": "Rsi(Close,14)",
    "rsi_delta": "Rsi(Close,14) - Ref(Rsi(Close,14),5)",       # RSI 5日变化

    # --- 波动率 Volatility ---
    "vol_5d": "Std(Returns(Close,1),5)",
    "vol_10d": "Std(Returns(Close,1),10)",
    "vol_20d": "Std(Returns(Close,1),20)",
    "vol_ratio_5_20": "Std(Returns(Close,1),5)/(Std(Returns(Close,1),20)+1e-9)",  # 短长波动比
    "vol_of_vol": "Std(Std(Returns(Close,1),5),20)",           # 波动的波动
    "range_pct": "(High-Low)/Close",                           # 当日振幅
    "range_ma_ratio": "((High-Low)/Close)/(Mean((High-Low)/Close,20)+1e-9)",
    "ret_skew_20": "Skew(Returns(Close,1),20)",
    "ret_kurt_20": "Kurt(Returns(Close,1),20)",

    # --- 量能 Volume ---
    "vol_ratio_5": "Volume/(Mean(Volume,5)+1e-9)",
    "vol_ratio_20": "Volume/(Mean(Volume,20)+1e-9)",
    "amt_mom": "Mean(Volume,5)/(Mean(Volume,20)+1e-9) - 1",    # 量能动量

    # --- 价格位置 Price position ---
    "pos_10d": "(Close-Tsmin(Low,10))/(Tsmax(High,10)-Tsmin(Low,10)+1e-9)",
    "pos_20d": "(Close-Tsmin(Low,20))/(Tsmax(High,20)-Tsmin(Low,20)+1e-9)",
    "pos_60d": "(Close-Tsmin(Low,60))/(Tsmax(High,60)-Tsmin(Low,60)+1e-9)",
    "dist_high_20": "Close/Tsmax(High,20) - 1",                # 距20日高点
    "dist_low_20": "Close/Tsmin(Low,20) - 1",                  # 距20日低点
    "tsrank_close_20": "Tsrank(Close,20)",                     # 现价在20日的时序分位
    "bb_pos_20": "(Close-Mean(Close,20))/(Std(Close,20)+1e-9)",  # 布林带位置

    # --- 价量关系 & 情绪 Price-volume & sentiment ---
    "pv_corr_10": "Corr(Close,Volume,10)",                     # 价量相关
    "pvret_corr_10": "Corr(Returns(Close,1),Returns(Volume,1),10)",  # 收益-量变相关
    "up_days_10": "Mean(Sign(Returns(Close,1)),10)",          # 近10天上涨占比(-1..1)
}

# 供 model 精确取用的特征列名 = 因子库的键 | feature columns = factor-library keys
FEATURE_COLS: list[str] = list(FACTORS.keys())


def compute_factors(df: pd.DataFrame, names=None) -> pd.DataFrame:
    """在一张 OHLCV 表上批量求值因子,返回 (日期 × 因子) 表。
    Evaluate factors on an OHLCV table; return a (dates × factors) table."""
    names = names or FEATURE_COLS
    out = {name: evaluate(FACTORS[name], df) for name in names}
    return pd.DataFrame(out, index=df.index).replace([np.inf, -np.inf], np.nan)


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV + 全部因子列(不改原表)。| OHLCV + all factor columns (does not modify original)."""
    return pd.concat([df.copy(), compute_factors(df)], axis=1)
