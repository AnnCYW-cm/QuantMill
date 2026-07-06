# -*- coding: utf-8 -*-
"""
test_e2e.py —— 端到端(用随包内置样本面板,离线)
test_e2e.py —— end-to-end on the bundled sample panel (offline)
=====================================================================
证明"装上即试":不联网,用内置样本跑通 面板 → IC → 打分 → top-k 回测。
"""

from quantmill.cross import (composite_score, factor_columns, ic_table,
                             load_sample_panel, topk_backtest)


def test_sample_panel_loads():
    p = load_sample_panel()
    assert list(p.index.names) == ["date", "symbol"]
    assert "fwd" in p.columns
    assert p.index.get_level_values("symbol").nunique() >= 10
    assert len(p) > 1000


def test_e2e_ic_table():
    p = load_sample_panel()
    tab = ic_table(p, factor_columns(p))
    assert len(tab) > 0
    assert {"factor", "IC", "ICIR"} <= set(tab.columns)


def test_e2e_composite_backtest():
    """稳健因子组合 → top-k 回测,整条链离线跑通并产出指标+曲线。"""
    p = load_sample_panel()
    res = topk_backtest(p, composite_score(p), k=5, horizon=20, cost=0.0015)
    assert "策略 top-k" in res["metrics"]
    assert "基准 等权" in res["metrics"]
    assert len(res["equity"]) > 0
    assert "超额年化" in res["metrics"]["策略 top-k"]


def test_sample_run_backtest_with_credibility():
    """CLI 同款样本回测应连 DSR 可信度试算一起离线跑通。"""
    from quantmill.cross.run import run_backtest
    res = run_backtest(sample=True, k=20, horizon=20, credibility=True)
    assert len(res["equity"]) > 0
    assert "dsr" in res
