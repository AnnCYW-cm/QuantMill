# -*- coding: utf-8 -*-
"""
cross —— 横截面选股 | cross-sectional stock selection
=====================================================================
和现有「每只票单独时序建模」不同,这一层把全市场堆成一张面板,
让模型学「同一天里哪只票比哪只强」——这是能真正选股的范式。
Unlike the per-symbol time-series path, this layer stacks the whole
universe into one panel so the model learns *relative* strength.

    universe.py  股票池(CSI300 成分股) | investable universe
    panel.py     横截面面板构建          | cross-sectional panel
    ic.py        横截面 IC(按天排名相关) | cross-sectional IC
"""
from __future__ import annotations

from quantmill.cross.universe import csi300, sample, universe, csi300_pit
from quantmill.cross.panel import build_panel, factor_columns, VALUE_COLS
from quantmill.cross.ic import daily_ic, ic_summary, ic_table
from quantmill.cross.model import rank_normalize, walk_forward_scores
from quantmill.cross.backtest import topk_backtest
from quantmill.cross.composite import composite_score, ROBUST_RECIPE
from quantmill.cross.run import get_panel, run_ic, run_backtest, run_validate, run_survivorship

__all__ = [
    "csi300", "sample", "universe",
    "build_panel", "factor_columns", "VALUE_COLS",
    "daily_ic", "ic_summary", "ic_table",
    "rank_normalize", "walk_forward_scores", "topk_backtest",
    "composite_score", "ROBUST_RECIPE", "csi300_pit",
    "get_panel", "run_ic", "run_backtest", "run_validate", "run_survivorship",
]
