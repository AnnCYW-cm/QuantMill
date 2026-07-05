# -*- coding: utf-8 -*-
"""
credibility —— 可信度层(平台护城河)| Credibility layer (the platform's moat)
================================================================================
把"这策略到底是真优势还是运气 + 过拟合"讲透:
  stats     统计严谨检验:DSR 去膨胀夏普、PBO 回测过拟合概率
  validate  批量广度检验 + 参数稳健性检验 + 汇总体检报告
Statistical rigor (DSR/PBO) + breadth & robustness batch validation.
"""

from quantmill.credibility.stats import (
    sharpe,
    expected_max_sharpe,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)
from quantmill.credibility.validate import (
    breadth,
    robustness,
    run_all,
    generate_report,
    compute_proba,
    DEFAULT_UNIVERSE,
    QUICK_UNIVERSE,
)

__all__ = [
    "sharpe", "expected_max_sharpe", "deflated_sharpe_ratio",
    "probability_of_backtest_overfitting",
    "breadth", "robustness", "run_all", "generate_report", "compute_proba",
    "DEFAULT_UNIVERSE", "QUICK_UNIVERSE",
]
