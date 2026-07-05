# -*- coding: utf-8 -*-
"""
test_features.py —— 特征工程的正确性,重中之重:没有未来函数
test_features.py —— Feature correctness; above all: NO look-ahead
================================================================
"""

import numpy as np
import pandas as pd

from quantmill.factor import make_features, make_label, build_dataset, FEATURE_COLS
from tests.conftest import make_ohlcv


def test_no_lookahead_features_only_use_past():
    """★核心★ 特征在第 t 天的值,只能由前 t 天的数据决定。
    ★CORE★ A feature's value at day t must depend only on data up to day t.
    做法:把行情截断到前 k 天,重算特征;前 k 天的特征值必须和用【全量】算出来的一模一样。
    若某个特征偷看了未来,截断后它的历史值就会变——测试就会失败。
    """
    df = make_ohlcv(300, seed=1)
    k = 200
    full = make_features(df)
    trunc = make_features(df.iloc[:k])          # 只喂前 k 天 | feed only the first k days

    for col in FEATURE_COLS:
        a = full.loc[trunc.index, col].to_numpy()   # 全量算出的前 k 天 | from full data
        b = trunc[col].to_numpy()                    # 截断算出的前 k 天 | from truncated data
        # equal_nan:开头 rolling 不足的 NaN 也要一致 | leading NaNs must match too
        assert np.allclose(a, b, equal_nan=True), f"特征 {col} 疑似偷看未来!"


def test_all_feature_cols_exist():
    """make_features 必须产出 FEATURE_COLS 里声明的每一列。| Every declared feature column must exist."""
    out = make_features(make_ohlcv(120))
    for col in FEATURE_COLS:
        assert col in out.columns


def test_make_label_direction_and_tail_nan():
    """标注 = 未来 horizon 天的涨跌;最后 horizon 行未来未知,必须是 NaN。
    Label = up/down over the next horizon days; the last horizon rows are NaN (future unknown)."""
    # 严格单调上涨的收盘价 | strictly increasing close
    close = pd.Series(np.arange(1, 21, dtype=float),
                      index=pd.bdate_range("2020-01-01", periods=20))
    df = pd.DataFrame({"Close": close})
    horizon = 5
    label = make_label(df, horizon=horizon)

    # 上涨序列:能算出的标注应全为 1 | rising series: all computable labels are 1
    assert (label.dropna() == 1).all()
    # 最后 horizon 行必须 NaN | last horizon rows must be NaN
    assert label.iloc[-horizon:].isna().all()
    # 倒数第 horizon+1 行应有值(未来可知)| the row just before must be known
    assert not np.isnan(label.iloc[-horizon - 1])


def test_make_label_down_series():
    """下跌序列:标注应为 0。| Falling series: labels should be 0."""
    close = pd.Series(np.arange(20, 0, -1, dtype=float),
                      index=pd.bdate_range("2020-01-01", periods=20))
    label = make_label(pd.DataFrame({"Close": close}), horizon=3)
    assert (label.dropna() == 0).all()


def test_build_dataset_clean_and_binary():
    """build_dataset 产出的 X 无 NaN、列正好是 FEATURE_COLS、y 是 0/1 且与 X 对齐。
    X has no NaN, columns == FEATURE_COLS, y is binary and index-aligned with X."""
    X, y, feat_df = build_dataset(make_ohlcv(300), horizon=5)
    assert list(X.columns) == FEATURE_COLS
    assert not X.isna().any().any()               # 无 NaN | no NaN
    assert set(y.unique()).issubset({0, 1})       # 只有 0/1 | binary only
    assert (X.index == y.index).all()             # 对齐 | aligned
    assert len(X) > 0
