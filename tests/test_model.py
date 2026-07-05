# -*- coding: utf-8 -*-
"""test_model.py —— walk_forward 必须是【样本外】,且概率合法 | walk_forward must be out-of-sample"""

import numpy as np
import pandas as pd

from quantmill.model import walk_forward
from quantmill.factor import build_dataset
from tests.conftest import make_ohlcv


def test_walk_forward_is_out_of_sample_and_valid_proba():
    """walk_forward:
    ① 返回序列与 X 同索引;
    ② 最开头那段(仅用于最初训练、从未被预测)必须是 NaN —— 证明没拿未来数据回填;
    ③ 有预测的地方,概率都在 [0,1]。
    ① same index as X; ② the leading warm-up part is NaN (never predicted) — proving no
    future backfill; ③ where predicted, probabilities lie in [0,1].
    """
    X, y, _ = build_dataset(make_ohlcv(400, seed=2), horizon=5)
    proba = walk_forward(X, y, n_splits=5)

    assert (proba.index == X.index).all()          # 同索引 | same index
    assert proba.isna().any()                       # 开头有 NaN | leading NaN exists
    assert proba.iloc[0] != proba.iloc[0] or np.isnan(proba.iloc[0])  # 第一行是 NaN | first row NaN

    valid = proba.dropna()
    assert len(valid) > 0
    assert ((valid >= 0) & (valid <= 1)).all()      # 概率合法 | valid probabilities


def test_walk_forward_never_predicts_first_fold():
    """TimeSeriesSplit 下,最前面约 1/(n_splits+1) 的样本永远进不了测试集 -> 必须是 NaN。
    Under TimeSeriesSplit the earliest ~1/(n_splits+1) of samples are never in any test
    set -> must be NaN (never predicted using later-trained models)."""
    X, y, _ = build_dataset(make_ohlcv(400, seed=3), horizon=5)
    n_splits = 5
    proba = walk_forward(X, y, n_splits=n_splits)
    warmup = len(X) // (n_splits + 1)
    # 预热段全 NaN | warm-up segment is all NaN
    assert proba.iloc[:warmup].isna().all()
