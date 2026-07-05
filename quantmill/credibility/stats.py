# -*- coding: utf-8 -*-
"""
credibility.py —— 可信度层:统计严谨的抗过拟合体检(平台护城河)
credibility.py —— Credibility layer: statistically rigorous overfit checks (the moat)
=====================================================================================
把"这策略到底是真优势还是运气 + 过拟合"讲透。两把学术标准尺子:

  1. DSR 去膨胀夏普 Deflated Sharpe Ratio(Bailey & López de Prado 2014)
     校正两大业绩膨胀源:①在 N 组参数里挑最好的(多重检验选择偏差);②收益非正态(偏度/峰度)。
     输出"真实夏普 > 0 的概率"。普通夏普不做这个校正,会把运气当本事。
     Corrects selection bias under N trials + non-normal returns; returns P(true Sharpe > 0).

  2. PBO 回测过拟合概率 Probability of Backtest Overfitting(Bailey et al. 2017, CSCV)
     用组合对称交叉验证:样本内最优的配置,在样本外有多大概率跌到中位数以下。
     ≈0.5 表示"挑参数纯靠运气"(完全过拟合);越低越好。
     Combinatorially Symmetric Cross-Validation: how often the in-sample best config
     underperforms the median out-of-sample. ~0.5 = pure overfitting.

铁律呼应(调研核心证据):McLean-Pontiff 发表后因子收益掉 58%;仅约 3 次独立尝试
就能在噪声上造出"很可能是假"的策略。所以【必须把"试了多少次 N"纳入显著性判断】。
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
from scipy.stats import norm, skew, kurtosis

_EULER = 0.5772156649015329  # 欧拉-马歇罗尼常数 | Euler–Mascheroni constant


def sharpe(returns) -> float:
    """单期(未年化)夏普 = 均值/标准差。| Per-period (non-annualized) Sharpe = mean/std."""
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    sd = r.std(ddof=1)
    if sd == 0 or len(r) < 2:
        return 0.0
    return float(r.mean() / sd)


def expected_max_sharpe(sr_trials, n_trials: int | None = None) -> float:
    """
    在 N 组"纯运气"的尝试里,预期能挑出的最大(单期)夏普 —— 即"基准噪声水平"。
    Expected maximum Sharpe achievable by chance across N trials (the null benchmark).
    公式来自 Bailey & López de Prado:SR0 = sqrt(Var(SR_trials)) · [(1-γ)·Z⁻¹(1-1/N) + γ·Z⁻¹(1-1/(N·e))]
    """
    sr = np.asarray(sr_trials, dtype=float)
    sr = sr[~np.isnan(sr)]
    if n_trials is None:
        n_trials = len(sr)
    if n_trials < 2 or len(sr) < 2:
        return 0.0
    var_sr = sr.var(ddof=1)
    if var_sr <= 0:
        return 0.0
    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(var_sr) * ((1.0 - _EULER) * z1 + _EULER * z2))


def deflated_sharpe_ratio(returns, sr_trials=None, sr0: float | None = None,
                          n_trials: int | None = None) -> dict:
    """
    去膨胀夏普比率:给定获胜策略的收益序列 + 所有尝试的夏普分布,输出真实夏普>0 的概率。
    Deflated Sharpe Ratio: P(true Sharpe > 0) after correcting for N trials + non-normality.

    参数 / Args:
        returns  : 获胜策略的单期收益序列(用于算其夏普、样本长度 T、偏度、峰度)
        sr_trials: 所有尝试配置的单期夏普数组(用于估计基准噪声 SR0)。给了它就自动算 SR0
        sr0      : 也可直接指定基准夏普(单期口径),与 sr_trials 二选一
        n_trials : 尝试次数 N(默认取 sr_trials 长度)

    返回 / Returns: {dsr, sr, sr0, T, skew, kurt, n_trials}
        dsr 是 [0,1] 概率:>0.95 通常视为"扣除多重检验后仍显著"。
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    T = len(r)
    sr = sharpe(r)
    sk = float(skew(r)) if T > 2 else 0.0
    ku = float(kurtosis(r, fisher=False)) if T > 3 else 3.0  # 非超额峰度 | non-excess kurtosis

    if sr0 is None:
        if sr_trials is None:
            raise ValueError("需要 sr_trials 或 sr0 之一 | need sr_trials or sr0")
        sr0 = expected_max_sharpe(sr_trials, n_trials)
        if n_trials is None:
            n_trials = len(np.asarray(sr_trials))

    # DSR = Φ[ (SR - SR0)·sqrt(T-1) / sqrt(1 - skew·SR + (kurt-1)/4·SR²) ]
    denom = np.sqrt(max(1e-12, 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2))
    z = (sr - sr0) * np.sqrt(max(T - 1, 1)) / denom
    dsr = float(norm.cdf(z))
    return {"dsr": dsr, "sr": sr, "sr0": float(sr0), "T": T,
            "skew": sk, "kurt": ku, "n_trials": n_trials}


def probability_of_backtest_overfitting(returns_matrix, n_splits: int = 10) -> dict:
    """
    PBO —— 组合对称交叉验证(CSCV)。
    PBO via CSCV. 输入 = 策略×时间 的收益矩阵(每列一个参数配置的单期收益序列)。

    做法:把时间轴切成 S 段,枚举所有"一半做样本内、另一半做样本外"的组合;
    每次在样本内选夏普最高的配置,看它在样本外的排名分位;若跌到中位数以下记为"过拟合"。
    PBO = 过拟合发生的比例。~0.5=挑参数纯靠运气;<0.5 越低越好。

    返回 / Returns: {pbo, n_configs, n_combos, logits(list)}
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2 or M.shape[1] < 2:
        raise ValueError("需要 (T, 配置数≥2) 的收益矩阵 | need (T, n_configs>=2) matrix")
    T, n_cfg = M.shape
    if n_splits % 2 != 0:
        n_splits += 1
    n_splits = min(n_splits, T)  # 段数不能超过样本数 | can't exceed sample count

    chunks = np.array_split(np.arange(T), n_splits)
    logits = []
    for train_ids in combinations(range(n_splits), n_splits // 2):
        train_rows = np.concatenate([chunks[i] for i in train_ids])
        test_rows = np.concatenate([chunks[i] for i in range(n_splits)
                                    if i not in train_ids])
        is_perf = np.array([sharpe(M[train_rows, c]) for c in range(n_cfg)])
        oos_perf = np.array([sharpe(M[test_rows, c]) for c in range(n_cfg)])
        n_star = int(np.nanargmax(is_perf))          # 样本内最优 | in-sample best
        # 样本外相对排名 ω∈(0,1):n_star 的 OOS 表现在所有配置中的分位
        rank = float((oos_perf <= oos_perf[n_star]).sum())  # 1..n_cfg
        omega = rank / (n_cfg + 1.0)
        omega = min(max(omega, 1e-6), 1.0 - 1e-6)
        logits.append(np.log(omega / (1.0 - omega)))       # λ<0 => 跌破中位 => 过拟合

    logits = np.asarray(logits)
    pbo = float((logits < 0).mean())
    return {"pbo": pbo, "n_configs": n_cfg, "n_combos": len(logits),
            "logits": logits.tolist()}


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    # 1) 一个"真有优势"的策略(正漂移) + 一堆纯噪声尝试
    good = rng.normal(0.001, 0.01, 750)          # 单期 SR≈0.1,较强
    noise_trials = [sharpe(rng.normal(0, 0.01, 750)) for _ in range(50)]
    d = deflated_sharpe_ratio(good, sr_trials=noise_trials + [sharpe(good)])
    print(f"真优势策略 DSR = {d['dsr']:.3f}  (SR={d['sr']:.3f} vs 基准SR0={d['sr0']:.3f}, N={d['n_trials']})")

    # 2) 纯噪声矩阵的 PBO 应≈0.5
    noise_matrix = rng.normal(0, 0.01, (600, 20))
    p = probability_of_backtest_overfitting(noise_matrix, n_splits=10)
    print(f"纯噪声矩阵 PBO = {p['pbo']:.3f}  (应≈0.5, 配置数={p['n_configs']}, 组合数={p['n_combos']})")
