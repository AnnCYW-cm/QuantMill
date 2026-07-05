# -*- coding: utf-8 -*-
"""
test_cross.py —— 横截面选股(面板 / 横截面IC / walk-forward模型 / top-k回测)
test_cross.py —— cross-sectional selection: panel / IC / walk-forward / backtest
===================================================================================
全部用合成行情,不联网。重点锁死:walk-forward 打分【不偷看未来】。
"""

import numpy as np
import pandas as pd

from quantmill.factor.library import FEATURE_COLS, compute_factors
from quantmill.cross.ic import daily_ic, ic_summary, ic_table
from quantmill.cross.model import rank_normalize, walk_forward_scores
from quantmill.cross.backtest import topk_backtest
from quantmill.cross.universe import universe, sample
from tests.conftest import make_ohlcv


# ---- 造一张合成横截面面板(多只票堆叠)| synthetic cross-sectional panel ----
def make_panel(nsym=8, n=300, horizon=5, seed=0):
    frames = []
    for s in range(nsym):
        df = make_ohlcv(n, seed=seed + s)
        feats = compute_factors(df)
        feats["fwd"] = df["Close"].shift(-horizon) / df["Close"] - 1
        feats = feats.reset_index()
        feats.columns = ["date"] + list(feats.columns[1:])
        feats["symbol"] = f"S{s}"
        frames.append(feats)
    return pd.concat(frames, ignore_index=True).set_index(["date", "symbol"]).sort_index()


# 快速、可复现、无 bagging 随机 => 完全确定性 | deterministic params for tests
DET = dict(n_estimators=40, learning_rate=0.1, num_leaves=15, min_child_samples=20,
           subsample=1.0, colsample_bytree=1.0, random_state=0, n_jobs=1,
           verbose=-1, deterministic=True)


def _cols(panel, k=8):
    return [c for c in FEATURE_COLS if c in panel.columns][:k]


# ---------------------------------------------------------------- 面板 | panel
def test_panel_structure():
    panel = make_panel()
    assert list(panel.index.names) == ["date", "symbol"]
    assert "fwd" in panel.columns
    assert panel.index.get_level_values("symbol").nunique() == 8


# ---------------------------------------------------------------- 横截面 IC | cross IC
def test_cross_ic_perfect_and_null():
    """因子==未来收益 => 每日横截面 IC≈1;纯噪声 => IC≈0。"""
    panel = make_panel(nsym=12, n=200)
    p = panel.dropna(subset=["fwd"]).copy()
    p["cheat"] = p["fwd"]                                   # 完美因子
    rng = np.random.default_rng(0)
    p["noise"] = rng.normal(size=len(p))                   # 纯噪声
    assert daily_ic(p, "cheat").mean() > 0.99
    assert abs(daily_ic(p, "noise").mean()) < 0.15


def test_ic_table_sorted_by_abs():
    panel = make_panel()
    tab = ic_table(panel, _cols(panel))
    assert list(tab.columns[:4]) == ["factor", "IC", "ICIR", "t"]
    aic = tab["absIC"].dropna().to_numpy()
    assert np.all(aic[:-1] >= aic[1:] - 1e-9)              # 降序 | descending


# ---------------------------------------------------------------- 归一化 | rank-normalize
def test_rank_normalize_in_unit_range():
    panel = make_panel()
    cols = _cols(panel)
    r = rank_normalize(panel, cols)
    assert r.min().min() >= 0.0 and r.max().max() <= 1.0
    assert not r.isna().any().any()                        # NaN 被填 0.5


# ------------------------------------------------ walk-forward 无未来函数 | NO LOOKAHEAD
def test_walk_forward_is_out_of_sample_only():
    """训练期之前的日期不该有样本外打分(只在 init_train 之后出分)。"""
    panel = make_panel(nsym=8, n=300)
    cols = _cols(panel)
    score = walk_forward_scores(panel, cols, horizon=5, init_train=120, step=40, params=DET)
    dates = panel.index.get_level_values("date").unique().sort_values()
    scored_dates = score.index.get_level_values("date").unique()
    assert scored_dates.min() >= dates[120]                # 初始训练窗内没有打分


def test_walk_forward_no_future_leak():
    """核心锁:砍掉未来数据,不改变过去日期的打分 —— 证明没偷看未来。
    Truncating future data must not change past scores => no lookahead."""
    panel = make_panel(nsym=8, n=320, seed=3)
    cols = _cols(panel)
    dates = panel.index.get_level_values("date").unique().sort_values()
    cut = dates[210]

    full = walk_forward_scores(panel, cols, horizon=5, init_train=120, step=40, params=DET)
    trunc_panel = panel[panel.index.get_level_values("date") <= cut]
    trunc = walk_forward_scores(trunc_panel, cols, horizon=5, init_train=120, step=40, params=DET)

    common = full.index.intersection(trunc.index)
    assert len(common) > 20                                # 有可比较的重叠打分
    assert np.allclose(full.loc[common].to_numpy(),
                       trunc.loc[common].to_numpy(), atol=1e-9)


# ---------------------------------------------------------------- 回测 | backtest
def test_topk_backtest_keys_and_shapes():
    panel = make_panel(nsym=30, n=260)
    cols = _cols(panel)
    score = walk_forward_scores(panel, cols, horizon=5, init_train=120, step=40, params=DET)
    res = topk_backtest(panel, score, k=6, horizon=5, cost=0.001)
    assert set(res["metrics"]) == {"策略 top-k", "基准 等权"}
    assert {"long", "bench"} <= set(res["equity"].columns)
    assert "超额年化" in res["metrics"]["策略 top-k"]


def test_topk_backtest_long_short_adds_ls():
    panel = make_panel(nsym=30, n=260)
    cols = _cols(panel)
    score = walk_forward_scores(panel, cols, horizon=5, init_train=120, step=40, params=DET)
    res = topk_backtest(panel, score, k=6, horizon=5, long_short=True)
    assert "多空 L/S" in res["metrics"]
    assert "ls" in res["equity"].columns


# ---------------------------------------------------------------- 稳健组合 | composite
def test_composite_score_fixed_recipe():
    """稳健因子组合:固定配方、零训练、打分不含 NaN 主体、名为 score。"""
    from quantmill.cross.composite import composite_score
    panel = make_panel(nsym=12, n=200)
    s = composite_score(panel)                             # 合成面板含配方里的量价因子
    assert s.name == "score"
    assert s.notna().sum() > len(s) * 0.5                  # 主体有值
    assert s.min() >= -1.0 and s.max() <= 1.0              # 分位加权,落在合理范围


# ---------------------------------------------------------------- 股票池 | universe
def test_universe_by_market():
    assert len(universe("us")) >= 10
    assert len(universe("hk")) >= 10
    assert universe("us", n=5) == universe("us")[:5]
    assert len(sample(5)) == 5
