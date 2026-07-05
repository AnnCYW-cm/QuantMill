# -*- coding: utf-8 -*-
"""
test_niche.py —— 散户结构性机会验证(离线,合成/样本数据)
test_niche.py —— retail niche edges (offline, synthetic/sample data)
"""

import pandas as pd

from quantmill.niche import analyze_cb_ipo, analyze_etf_premium, load_sample_cb


def test_load_sample_cb():
    df = load_sample_cb()
    assert {"first_day_return", "list_year"} <= set(df.columns)
    assert len(df) > 100


def test_cb_marketing_vs_honest_dilution():
    """核心:营销首日收益为正,但扣中签率后每账户年化期望被稀释到很小。"""
    df = load_sample_cb()
    r = analyze_cb_ipo(df, win_rate=0.0004, max_hands=1000)
    assert 0 <= r["break_rate"] <= 100
    assert r["mean_first_day"] > 0                 # 样本整体正收益(营销口径)
    assert 0 < r["ev_yuan_per_year"] < 5000        # 诚实口径:被中签率稀释到几百~几千元/账户
    assert "by_year" in r and len(r["by_year"]) >= 3


def test_etf_exploitable_after_cost():
    df = pd.DataFrame({"code": ["510300", "159915", "512000"],
                       "name": ["a", "b", "c"],
                       "premium": [0.005, -0.0003, 0.03]})
    r = analyze_etf_premium(df, cost=0.002)
    assert r["n_etf"] == 3
    assert r["n_exploitable"] == 2                 # 0.005 和 0.03 超成本,-0.0003 不够
    assert len(r["top"]) == 2
    assert r["top"][0]["premium%"] == 3.0          # 最大的排最前
