# -*- coding: utf-8 -*-
"""
risk —— 风控/仓位层 | risk management & position sizing
=====================================================================
投资经理视角:alpha 弱的时候,决定生死的是【仓位和回撤】,不是又一个因子。
这一层把"等权满仓"的选股回测,套上真实资金管理会做的四件事:

  1. 逆波动加权     每只等风险贡献,而非等金额(单只暴动不至于掀翻组合)
  2. 集中度上限     单只权重封顶,防 top-k 全挤一处
  3. 波动率目标     按组合近期实现波动缩放总敞口 → 稳定风险预算(高波时降仓)
  4. 回撤开关       净值从高点回撤超阈值就自动降仓,回补后恢复(生存机制)

全部严格因果(只用过去):波动/回撤都取到上一期为止,绝不偷看当期。
"""
from __future__ import annotations

from quantmill.risk.overlay import inverse_vol_weights, risk_managed_backtest

__all__ = ["inverse_vol_weights", "risk_managed_backtest"]
