"""
state.py —— 网页各蓝图共享的内存缓存 | shared in-memory caches across blueprints
=====================================================================
都是可变 dict,只增删键、从不整体重赋值,故各模块 `from ... import` 后共享同一对象。
"""
from __future__ import annotations

_QCACHE: dict = {}    # market -> (ts, quotes)         行情
_SCACHE: dict = {}    # market -> signals              信号
_CCACHE: dict = {}    # market -> credibility          可信度
_SPROG: dict = {}     # market -> 信号计算进度          signal-compute progress
_XCACHE: dict = {}    # market:model -> 横截面结果      cross-sectional result
_XPROG: dict = {}     # market:model -> 横截面进度      cross-compute progress
_QSRC: dict = {}      # market -> 行情源(alpaca/yfinance)
_BCACHE: dict = {}    # (market, method) -> 组合回测结果 portfolio backtest
