# -*- coding: utf-8 -*-
"""
test_factor.py —— 因子引擎 / 因子库 / IC 分析的正确性
test_factor.py —— Factor engine / library / IC analysis correctness
===================================================================
"""

import numpy as np
import pandas as pd

from quantmill.factor.expr import evaluate, Ref, Delta, Mean
from quantmill.factor.library import FACTORS, FEATURE_COLS, compute_factors, make_features
from quantmill.factor import build_dataset
from quantmill.factor.analysis import forward_return, factor_ic, ic_report, quantile_returns
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------- 引擎算子 | operators
def test_operators_basic():
    """Ref/Delta/Mean 语义正确。| Ref/Delta/Mean semantics."""
    x = pd.Series([1.0, 2.0, 4.0, 7.0])
    assert Ref(x, 1).tolist()[1:] == [1.0, 2.0, 4.0]        # 前一期 | previous value
    assert Delta(x, 1).tolist()[1:] == [1.0, 2.0, 3.0]      # 差分 | difference
    assert Mean(x, 2).tolist()[-1] == (4.0 + 7.0) / 2       # 2期均值 | 2-period mean


def test_evaluate_matches_manual():
    """表达式求值 == 手写 pandas。| Expression eval equals hand-written pandas."""
    df = make_ohlcv(120, seed=1)
    got = evaluate("Close/Mean(Close,20) - 1", df)
    manual = df["Close"] / df["Close"].rolling(20).mean() - 1
    assert np.allclose(got.to_numpy(), manual.to_numpy(), equal_nan=True)


def test_evaluate_restricted_namespace():
    """受限命名空间:内建被禁用(安全)。| Builtins are blocked (safety)."""
    df = make_ohlcv(50)
    try:
        evaluate("__import__('os').getcwd()", df)
        assert False, "应禁止内建 | builtins should be blocked"
    except Exception:
        pass


# ---------------------------------------------------------------- 因子库 | library
def test_library_reproduces_return_semantics():
    """因子库里的 ret_5d 就是 5 日收益率。| ret_5d equals 5-day pct_change."""
    df = make_ohlcv(200, seed=2)
    feats = make_features(df)
    assert np.allclose(feats["ret_5d"].to_numpy(),
                       df["Close"].pct_change(5).to_numpy(), equal_nan=True)


def test_compute_factors_all_present_no_inf():
    """所有因子都算得出、无 inf,列 == FEATURE_COLS。| All factors computed, no inf."""
    fac = compute_factors(make_ohlcv(300, seed=3))
    assert list(fac.columns) == FEATURE_COLS
    assert len(FEATURE_COLS) >= 40                          # 已从18扩到40+ | expanded
    assert not np.isinf(fac.to_numpy()).any()


def test_factor_no_lookahead():
    """★核心★ 因子在第 t 天的值只由前 t 天决定(截断重算不变)。
    ★CORE★ A factor's value at day t depends only on data up to t."""
    df = make_ohlcv(300, seed=4)
    k = 200
    full = compute_factors(df)
    trunc = compute_factors(df.iloc[:k])
    for col in FEATURE_COLS:
        a = full.loc[trunc.index, col].to_numpy()
        b = trunc[col].to_numpy()
        assert np.allclose(a, b, equal_nan=True), f"因子 {col} 疑似偷看未来!"


def test_build_dataset_still_works_with_expanded_factors():
    """扩到 40+ 因子后,build_dataset 仍产出干净、对齐、二值的数据集。"""
    X, y, feat_df = build_dataset(make_ohlcv(400, seed=5), horizon=5)
    assert list(X.columns) == FEATURE_COLS
    assert not X.isna().any().any()
    assert set(y.unique()).issubset({0, 1})
    assert len(X) > 100                                     # 扩因子后仍剩足够样本 | enough rows remain


# ---------------------------------------------------------------- IC 分析 | IC analysis
def test_ic_perfect_and_random():
    """完美因子(=未来收益)IC≈1;随机因子 IC≈0。| Perfect factor IC≈1, random ≈0."""
    df = make_ohlcv(400, seed=6)
    fwd = forward_return(df, horizon=5)
    ic_perfect, ric_perfect = factor_ic(fwd, fwd)          # 因子=未来收益(作弊)
    assert ric_perfect > 0.99
    rng = np.random.default_rng(0)
    rand = pd.Series(rng.normal(0, 1, len(df)), index=df.index)
    ic_rand, ric_rand = factor_ic(rand, fwd)
    assert abs(ric_rand) < 0.2


def test_ic_report_shape_and_sort():
    """ic_report 列齐、按 |RankIC| 降序。| ic_report columns + sorted desc by absRankIC."""
    rep = ic_report(make_ohlcv(400, seed=7), horizon=5)
    assert list(rep.columns) == ["factor", "IC", "RankIC", "absRankIC"]
    assert len(rep) == len(FEATURE_COLS)
    vals = rep["absRankIC"].dropna().to_numpy()
    assert (np.diff(vals) <= 1e-9).all()                   # 非升序 | non-increasing


def test_quantile_returns_monotonic_for_perfect_factor():
    """完美因子按分位,未来收益应单调递增。| Perfect factor -> monotonic quantile returns."""
    df = make_ohlcv(400, seed=8)
    fwd = forward_return(df, horizon=5)
    qr = quantile_returns(fwd, fwd, q=5)
    assert (np.diff(qr.to_numpy()) > 0).all()
