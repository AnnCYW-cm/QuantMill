"""
optimizer.py —— 组合配置器:信号截面 → 权重 | Portfolio allocators: signals → weights
=====================================================================================
把"某一天全体股票的信号 + 之前的收益窗口"变成"一份仓位分配"。长仓、权重和=1、可设单票上限。

  equal_weight_all   等权持有全部(忽略信号)—— 基准
  top_k_equal        选信号最高 top-k,等权
  inverse_vol        top-k 内按波动率倒数加权(低波动多配)
  min_variance       top-k 内最小方差(只用协方差,避开 MV 的噪声放大)—— 风险模型驱动

统一签名 allocator(signals, ret_window, k, max_weight):
  signals    当天各票信号(pd.Series)
  ret_window 之前一段每日收益(pd.DataFrame,日期×股票),用于估波动/协方差;可为 None
"""

from __future__ import annotations

import pandas as pd


def _apply_cap(w: pd.Series, max_weight: float | None) -> pd.Series:
    """限单票上限后重新归一。| Cap per-name weight then renormalize."""
    if not max_weight:
        return w
    for _ in range(10):
        over = w > max_weight
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        under = (w < max_weight) & (w > 0)
        if not under.any():
            break
        w[under] += excess * w[under] / w[under].sum()
    return w


def _top_k(signals: pd.Series, k: int | None) -> list:
    """选信号最高的 k 只(NaN 剔除)。| Pick top-k names by signal (drop NaN)."""
    s = signals.dropna()
    if s.empty:
        return []
    k = len(s) if k is None else min(k, len(s))
    return s.nlargest(k).index.tolist()


def _window_ok(ret_window, picks) -> bool:
    """收益窗口是否够长且含全部 picks(否则退化等权)。| Is the window usable."""
    return (ret_window is not None and len(ret_window) >= 5
            and all(p in ret_window.columns for p in picks))


def equal_weight_all(signals, ret_window=None, k=None, max_weight=None) -> pd.Series:
    """等权持有全部有信号的票(忽略信号强度)—— 基准。| Equal-weight all valid names."""
    valid = signals.dropna().index
    w = pd.Series(0.0, index=signals.index)
    if len(valid):
        w[valid] = 1.0 / len(valid)
    return w


def top_k_equal(signals, ret_window=None, k=None, max_weight=None) -> pd.Series:
    """选信号最高的 top-k,等权。| Top-k by signal, equal-weighted."""
    picks = _top_k(signals, k)
    w = pd.Series(0.0, index=signals.index)
    if picks:
        w[picks] = 1.0 / len(picks)
    return _apply_cap(w, max_weight)


def inverse_vol(signals, ret_window=None, k=None, max_weight=None) -> pd.Series:
    """top-k 内按波动率倒数加权;窗口不足则退化等权。| Top-k, inverse-vol weighted."""
    picks = _top_k(signals, k)
    w = pd.Series(0.0, index=signals.index)
    if not picks:
        return w
    if _window_ok(ret_window, picks):
        vol = ret_window[picks].std()
        inv = 1.0 / (vol.fillna(vol.mean()) + 1e-9)
        w[picks] = inv / inv.sum()
    else:
        w[picks] = 1.0 / len(picks)          # 窗口不足,退化等权 | fall back to equal
    return _apply_cap(w, max_weight)


def min_variance(signals, ret_window=None, k=None, max_weight=None) -> pd.Series:
    """top-k 内最小方差组合(用收缩协方差)。| Min-variance within top-k (shrinkage cov)."""
    from quantmill.portfolio.risk import min_variance_weights, shrinkage_cov

    picks = _top_k(signals, k)
    w = pd.Series(0.0, index=signals.index)
    if not picks:
        return w
    if _window_ok(ret_window, picks):
        cov = shrinkage_cov(ret_window[picks])
        mv = min_variance_weights(cov, max_weight=max_weight)
        w[mv.index] = mv.values
    else:
        w[picks] = 1.0 / len(picks)          # 窗口不足,退化等权 | fall back to equal
    return w


# 配置器注册表 | allocator registry
ALLOCATORS = {
    "equal": equal_weight_all,
    "topk": top_k_equal,
    "invvol": inverse_vol,
    "minvar": min_variance,
}
