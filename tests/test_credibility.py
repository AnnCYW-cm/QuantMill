# -*- coding: utf-8 -*-
"""
test_credibility.py —— 可信度层核心公式的正确性 | DSR & PBO correctness
=====================================================================
用无争议的方向性性质来锁(而非脆弱的精确数值):
- 试验次数越多 -> 噪声基准越高 -> DSR 越低(越难显著)
- 真有优势的策略(高夏普、试验少)-> DSR 接近 1
- 持续领先的配置 -> PBO 低;样本内赢样本外必输的配置 -> PBO 高
"""

import numpy as np

from quantmill.credibility.stats import (
    sharpe,
    expected_max_sharpe,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)


# ---------------------------------------------------------------- Sharpe
def test_sharpe_known_value():
    """单期夏普 = 均值/标准差。| Per-period Sharpe = mean/std."""
    r = np.array([0.01, -0.01, 0.02, 0.00, 0.03])
    assert abs(sharpe(r) - r.mean() / r.std(ddof=1)) < 1e-12


def test_sharpe_zero_variance():
    """零波动不炸,返回 0。| Zero variance returns 0, no crash."""
    assert sharpe(np.array([0.01, 0.01, 0.01])) == 0.0


# ---------------------------------------------------------------- 期望最大夏普
def test_expected_max_sharpe_increases_with_trials():
    """★ 试验次数越多,纯运气能挑出的最大夏普越高(基准噪声随 N 上升)。
    ★ More trials -> higher expected-max Sharpe achievable by chance."""
    rng = np.random.default_rng(0)
    sr_trials = rng.normal(0, 0.05, 30)          # 固定一批夏普(固定方差)
    ems5 = expected_max_sharpe(sr_trials, n_trials=5)
    ems50 = expected_max_sharpe(sr_trials, n_trials=50)
    ems500 = expected_max_sharpe(sr_trials, n_trials=500)
    assert ems5 < ems50 < ems500


# ---------------------------------------------------------------- DSR
def test_dsr_is_probability():
    """DSR 是 [0,1] 概率。| DSR is a probability in [0,1]."""
    rng = np.random.default_rng(1)
    r = rng.normal(0.0005, 0.01, 500)
    d = deflated_sharpe_ratio(r, sr_trials=rng.normal(0, 0.05, 20))["dsr"]
    assert 0.0 <= d <= 1.0


def test_dsr_decreases_with_more_trials():
    """★ 同一策略,试验次数越多,DSR 越低(挑得越多越可能是运气)。
    ★ Same strategy: more trials -> lower DSR."""
    rng = np.random.default_rng(2)
    r = rng.normal(0.0008, 0.01, 800)            # 中等强度策略
    sr_trials = rng.normal(0, 0.05, 40)          # 固定方差的一批试验夏普
    dsr_few = deflated_sharpe_ratio(r, sr_trials=sr_trials, n_trials=5)["dsr"]
    dsr_many = deflated_sharpe_ratio(r, sr_trials=sr_trials, n_trials=1000)["dsr"]
    assert dsr_many < dsr_few


def test_dsr_strong_strategy_high():
    """★ 很强的策略(高夏普)+ 试验少且方差小 -> DSR 接近 1。
    ★ Strong strategy with few low-variance trials -> DSR near 1."""
    rng = np.random.default_rng(3)
    r = rng.normal(0.003, 0.01, 1000)            # 单期夏普≈0.3,很强
    weak_trials = [0.0, 0.01, -0.01, 0.005, sharpe(r)]  # 少量近零 + 自己
    d = deflated_sharpe_ratio(r, sr_trials=weak_trials)["dsr"]
    assert d > 0.9


# ---------------------------------------------------------------- PBO
def test_pbo_is_probability():
    """PBO 是 [0,1] 概率。| PBO is a probability in [0,1]."""
    rng = np.random.default_rng(4)
    m = rng.normal(0, 0.01, (600, 12))
    p = probability_of_backtest_overfitting(m, n_splits=10)["pbo"]
    assert 0.0 <= p <= 1.0


def test_pbo_persistent_winner_is_low():
    """★ 有一列持续领先(真信号),样本内赢也样本外赢 -> PBO 低。
    ★ One consistently-superior column -> in-sample best is out-of-sample best -> low PBO."""
    rng = np.random.default_rng(5)
    m = rng.normal(0, 0.01, (800, 8))
    m[:, 0] += 0.004                              # 第0列全程正漂移=真持续优势
    p = probability_of_backtest_overfitting(m, n_splits=10)["pbo"]
    assert p < 0.25


def test_pbo_overfit_is_high():
    """★ 每列只在某一个时间段"发光"(样本内赢、样本外必平) -> PBO 高。
    ★ Each column spikes only in its own time block -> in-sample winner is out-of-sample
    mediocre -> high PBO (classic overfitting)."""
    rng = np.random.default_rng(6)
    n_blocks, n_cols, per = 10, 10, 100
    T = n_blocks * per
    m = rng.normal(0, 0.001, (T, n_cols))         # 极小噪声
    for i in range(n_cols):                        # 第 i 列只在第 i 段有大正收益
        m[i * per:(i + 1) * per, i] += 0.02
    p = probability_of_backtest_overfitting(m, n_splits=n_blocks)["pbo"]
    assert p > 0.6
