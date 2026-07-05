# -*- coding: utf-8 -*-
"""
niche —— 散户结构性机会验证 | retail structural-edge validation
=====================================================================
深度调研结论:免费横截面因子 alpha 真实但极弱;散户唯一有证据的真实机会
在 A股/港股的【结构性/机制性红利】——可转债打新、ETF 折溢价套利。
本包用平台一贯的"诚实"框架去【严格验证】它们到底还有多少肉,
把营销口径("首日均涨20%!")翻译成诚实口径(扣中签率/成本后的每账户期望)。

    cb_ipo.py    可转债打新:首日收益分布、破发率、扣中签率后每账户期望
    etf_arb.py   ETF 折溢价:当前可套利价差分布、扣成本后机会数、容量提醒
"""
from __future__ import annotations

from quantmill.niche.cb_ipo import (analyze_cb_ipo, fetch_cb_first_days,
                                    fetch_cb_universe, load_sample_cb)
from quantmill.niche.etf_arb import analyze_etf_premium, fetch_etf_premium

__all__ = [
    "fetch_cb_universe", "fetch_cb_first_days", "load_sample_cb", "analyze_cb_ipo",
    "fetch_etf_premium", "analyze_etf_premium",
]
