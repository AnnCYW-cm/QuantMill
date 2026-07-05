# -*- coding: utf-8 -*-
"""
backtest.py —— 组合级回测引擎 | Portfolio-level backtest engine
================================================================
从"信号面板 + 收益面板"到"一条组合资金曲线"。含风险模型与市场制度:

  vol_target   波动率目标:近期波动高时降仓(持币),压回撤——"先活下来"
  price_limit  涨跌停冻结:当日涨跌停锁死的票不可成交(A股 ±10%)
  sell_cost    卖出额外成本(A股印花税 0.05%)

机制铁律:权重在第 t 天决定、从第 t+1 天赚收益(⚠️无未来函数:weights.shift(1))。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantmill.portfolio.optimizer import ALLOCATORS
from quantmill.portfolio.risk import shrinkage_cov, portfolio_vol


def backtest_portfolio(signal_panel: pd.DataFrame, return_panel: pd.DataFrame,
                       method: str = "topk", k: int | None = None,
                       rebalance: int = 5, commission: float = 0.002,
                       vol_window: int = 20, max_weight: float | None = None,
                       vol_target: float | None = None, leverage_cap: float = 1.0,
                       price_limit: float | None = None,
                       sell_cost: float = 0.0) -> dict:
    """运行组合回测,返回资金曲线/收益/权重/成本。| Run portfolio backtest."""
    if method not in ALLOCATORS:
        raise ValueError(f"未知配置法 {method},可选 {list(ALLOCATORS)}")
    allocator = ALLOCATORS[method]

    return_panel = return_panel.sort_index()
    signal_panel = signal_panel.reindex(return_panel.index)
    dates, symbols = return_panel.index, return_panel.columns

    weights = pd.DataFrame(0.0, index=dates, columns=symbols)
    cost = pd.Series(0.0, index=dates)
    w = pd.Series(0.0, index=symbols)

    for i, dt in enumerate(dates):
        if i % rebalance == 0:
            sig = signal_panel.loc[dt].reindex(symbols)
            ret_window = return_panel.iloc[max(0, i - vol_window):i]  # 只用 t 之前 | before t
            new_w = allocator(sig, ret_window, k, max_weight).reindex(symbols).fillna(0.0)

            # 涨跌停冻结:当日锁死的票不可成交,权重保持不变,其余按目标重分配剩余额度
            if price_limit and i > 0:
                locked = (return_panel.loc[dt].abs() >= price_limit * 0.99) \
                    .reindex(symbols).fillna(False)
                if locked.any():
                    frozen = w[locked]
                    budget = max(0.0, 1.0 - float(frozen.sum()))
                    free = new_w[~locked]
                    free = free / free.sum() * budget if free.sum() > 0 else free
                    adj = pd.Series(0.0, index=symbols)
                    adj[locked] = frozen
                    adj[~locked] = free
                    new_w = adj

            # 波动率目标:近期组合波动超标就整体降仓(持币),不加杠杆
            if vol_target and len(ret_window) >= 5:
                held = new_w[new_w > 1e-9].index
                if len(held) >= 1:
                    pv = portfolio_vol(new_w[held], shrinkage_cov(ret_window[held]))
                    if pv > 0:
                        new_w = new_w * min(leverage_cap, vol_target / pv)

            # 成本:换手×手续费 + 卖出额×印花税 | turnover cost + sell stamp duty
            dw = new_w - w
            sell = float((-dw.clip(upper=0)).sum())
            cost.loc[dt] = float(dw.abs().sum()) * commission + sell * sell_cost
            w = new_w
        weights.loc[dt] = w

    # 权重 t 决定→t+1 生效(shift 1);成本随新权重生效日一起扣
    port_ret = (weights.shift(1).fillna(0.0) * return_panel).sum(axis=1) \
        - cost.shift(1).fillna(0.0)
    equity = (1.0 + port_ret.fillna(0.0)).cumprod()
    return {"equity": equity, "returns": port_ret, "weights": weights, "cost": cost}


def portfolio_metrics(result: dict, periods_per_year: int = 252) -> dict:
    """把回测结果提炼成关键指标。| Distill key metrics."""
    r = result["returns"].dropna()
    eq = result["equity"]
    if len(r) < 2 or len(eq) == 0:
        return {"total_return": 0.0, "sharpe": 0.0, "ann_return": 0.0,
                "ann_vol": 0.0, "max_drawdown": 0.0, "total_cost": 0.0}
    total_return = float(eq.iloc[-1] - 1.0)
    ann_return = float((1.0 + r).prod() ** (periods_per_year / len(r)) - 1.0)
    ann_vol = float(r.std() * np.sqrt(periods_per_year))
    sharpe = float(ann_return / ann_vol) if ann_vol > 0 else 0.0
    max_dd = float((eq / eq.cummax() - 1.0).min())
    return {
        "total_return": round(total_return * 100, 1),
        "sharpe": round(sharpe, 2),
        "ann_return": round(ann_return * 100, 1),
        "ann_vol": round(ann_vol * 100, 1),
        "max_drawdown": round(max_dd * 100, 1),
        "total_cost": round(float(result["cost"].sum()) * 100, 2),
    }
