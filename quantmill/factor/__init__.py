"""
factor —— 因子层 | Factor layer
================================
把原始 OHLCV 加工成"特征/因子表",并给数据打涨跌标注。
  expr      因子表达式引擎(时序算子,严格向后)
  library   因子库(40+ 因子,用表达式定义)+ make_features
  analysis  因子有效性分析(IC/RankIC/分位单调性)

两条铁律 / Two iron rules:
  1. 特征只能用"今天及以前"的数据(所有算子向后)。No look-ahead in features.
  2. 只有【标注 label】允许用未来收益,最新 horizon 行为 NaN 需丢掉。Only labels use the future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantmill import config
from quantmill.factor.library import (
    FACTORS,
    FEATURE_COLS,
    compute_factors,
    make_features,
)

__all__ = [
    "FACTORS", "FEATURE_COLS", "make_features", "compute_factors",
    "make_label", "build_dataset",
]


def make_label(df: pd.DataFrame, horizon: int = config.HORIZON) -> pd.Series:
    """
    打标注:未来 horizon 天之后是涨(1)还是跌(0)。
    Labeling: whether it rises (1) or falls (0) after horizon days.

    ⚠️ 这里用了 shift(-horizon) 偷看未来 —— 这是唯一允许偷看的地方(它是训练用的"答案")。
    ⚠️ shift(-horizon) peeks into the future — the ONLY place peeking is allowed (it's the label).
       最新 horizon 行的未来未知,会是 NaN。The latest horizon rows have unknown futures -> NaN.
    """
    future_ret = df["Close"].shift(-horizon) / df["Close"] - 1
    label = (future_ret > 0).astype(float)
    label[future_ret.isna()] = np.nan
    return label


def build_dataset(df: pd.DataFrame, horizon: int = config.HORIZON):
    """
    一步到位:原始行情 -> (特征表 X, 标注 y),对齐并去掉含 NaN 的行。
    One-stop: raw market data -> (feature table X, label y), aligned, NaN rows removed.

    返回 / Returns:
        X       : DataFrame,只含 FEATURE_COLS | features only
        y       : Series,0/1 标注 | binary labels
        feat_df : 完整特征表(含价格,供回测/画图)| full table incl. price
    """
    feat_df = make_features(df)
    feat_df["label"] = make_label(df, horizon)
    # 开头因 rolling 不足、结尾因未来未知,都是 NaN,一起丢掉
    clean = feat_df.dropna(subset=FEATURE_COLS + ["label"])
    X = clean[FEATURE_COLS]
    y = clean["label"].astype(int)
    return X, y, feat_df


if __name__ == "__main__":
    from quantmill.data import get_ohlcv

    df = get_ohlcv("AAPL", "us", start="2020-01-01", end="2024-01-01")
    X, y, feat_df = build_dataset(df, horizon=5)
    print(f"\n特征表规模:{X.shape[0]} 行 × {X.shape[1]} 个因子")
    print(f"标注分布:涨={int(y.sum())}  跌={int((1 - y).sum())}  涨占比={y.mean():.1%}")
