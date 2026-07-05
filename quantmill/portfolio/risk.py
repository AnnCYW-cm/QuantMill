# -*- coding: utf-8 -*-
"""
risk.py —— 风险模型 | Risk model
=================================
组合层的"先活下来"引擎:协方差估计 + 最小方差 + 组合波动率。
The "survive first" engine of the portfolio layer: covariance + min-variance + portfolio vol.

  shrinkage_cov       Ledoit-Wolf 收缩协方差(股票少时比样本协方差稳得多)
  portfolio_vol       给定权重的组合波动率(年化)
  min_variance_weights 只用协方差、不用预期收益的最小方差组合(长仓,避开 MV 的噪声放大)

为什么最小方差而非均值方差(MV)?
    协方差可估、预期收益基本不可估;MV 会把预期收益的估计误差放大成极端仓位(error maximization)。
    最小方差只依赖协方差,是稳健得多的风险模型用法。
    Min-variance uses only the (estimable) covariance, dodging MV's error maximization.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sample_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """样本协方差。| Sample covariance."""
    return returns.dropna().cov()


def shrinkage_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit-Wolf 收缩协方差;样本太短则退化为样本协方差。
    Ledoit-Wolf shrinkage covariance; falls back to sample cov if too few rows."""
    X = returns.dropna()
    if X.shape[0] < 5 or X.shape[1] < 2:
        return sample_cov(returns)
    try:
        from sklearn.covariance import LedoitWolf
        cov = LedoitWolf().fit(X.to_numpy()).covariance_
        return pd.DataFrame(cov, index=X.columns, columns=X.columns)
    except Exception:  # noqa: BLE001
        return sample_cov(returns)


def portfolio_vol(weights: pd.Series, cov: pd.DataFrame,
                  periods_per_year: int = 252) -> float:
    """组合年化波动率 = sqrt(wᵀΣw)·sqrt(252)。| Annualized portfolio volatility."""
    cols = cov.columns
    w = weights.reindex(cols).fillna(0.0).to_numpy()
    var = float(w @ cov.to_numpy() @ w)
    return float(np.sqrt(max(var, 0.0)) * np.sqrt(periods_per_year))


def min_variance_weights(cov: pd.DataFrame, max_weight: float | None = None) -> pd.Series:
    """
    长仓最小方差组合:min wᵀΣw, s.t. Σw=1, 0≤w≤max。用 scipy SLSQP 解小型二次规划。
    Long-only minimum-variance portfolio via scipy SLSQP.
    """
    cols = list(cov.columns)
    n = len(cols)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=cols)

    Sigma = cov.to_numpy()
    ub = max_weight if max_weight else 1.0
    ub = max(ub, 1.0 / n)                       # 上限不能低于等权,否则无解
    from scipy.optimize import minimize
    w0 = np.full(n, 1.0 / n)
    res = minimize(
        lambda w: float(w @ Sigma @ w), w0, method="SLSQP",
        bounds=[(0.0, ub)] * n,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
        options={"maxiter": 200, "ftol": 1e-10},
    )
    w = res.x if res.success else w0
    w = np.clip(w, 0, None)
    w = w / w.sum() if w.sum() > 0 else w0
    return pd.Series(w, index=cols)
