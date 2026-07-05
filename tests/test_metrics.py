# -*- coding: utf-8 -*-
"""test_metrics.py —— 回撤计算 + 汇总/判读逻辑 | drawdown + summarize/verdict logic"""

import pandas as pd

from quantmill.evaluation import buy_hold_max_drawdown, summarize, verdict


def test_buy_hold_max_drawdown_known_case():
    """已知序列 100->120->60->80:最大回撤 = 60/120 - 1 = -50%。
    Known series: max drawdown from peak 120 to trough 60 = -50%."""
    close = pd.Series([100.0, 120.0, 60.0, 80.0])
    assert abs(buy_hold_max_drawdown(close) - (-50.0)) < 1e-6


def test_buy_hold_no_drawdown_when_monotonic_up():
    """一路上涨:回撤为 0。| Monotonic up: drawdown is 0."""
    close = pd.Series([10.0, 11.0, 12.0, 13.0])
    assert abs(buy_hold_max_drawdown(close)) < 1e-6


def _fake_stats(ret, bh_ret, dd):
    """伪造一个 backtesting.py 风格的 stats(dict 足够,summarize 只按键取值)。
    Fake a backtesting.py-style stats (a dict suffices; summarize just indexes by key)."""
    return {
        "Start": pd.Timestamp("2020-01-01"), "End": pd.Timestamp("2021-01-01"),
        "Return [%]": ret, "Buy & Hold Return [%]": bh_ret,
        "Max. Drawdown [%]": dd, "Sharpe Ratio": 1.0,
        "# Trades": 10, "Win Rate [%]": 55.0,
    }


def test_summarize_flags_beat_and_smaller_drawdown():
    """策略收益更高 + 回撤更浅(更接近0)时,两个布尔标志都为真。
    When strategy return is higher and drawdown is shallower, both flags are True."""
    close = pd.Series([100.0, 90.0, 110.0])          # 买入持有回撤 = -10% | b&h dd = -10%
    s = summarize(_fake_stats(ret=50.0, bh_ret=20.0, dd=-5.0), close)
    assert s["跑赢买入持有"] is True                  # 50 > 20
    assert s["回撤更小"] is True                       # -5% 比 -10% 更浅 | shallower


def test_verdict_red_when_worse_on_both():
    """收益和回撤都更差 -> 红灯结论。| Worse on both -> red verdict."""
    close = pd.Series([100.0, 50.0, 60.0])           # 买入持有回撤 -50% | b&h dd -50%
    s = summarize(_fake_stats(ret=-30.0, bh_ret=20.0, dd=-60.0), close)
    assert "🔴" in verdict(s)
