# -*- coding: utf-8 -*-
"""test_backtest.py —— 回测集成(离线)+ 阈值行为 | backtest integration (offline) + threshold behavior"""

import numpy as np
import pandas as pd

from quantmill.factor import build_dataset
from quantmill.backtest import run_ml_backtest
from tests.conftest import make_ohlcv


def _proba_from_pattern(index, warmup=60):
    """伪造一段样本外信号:前 warmup 行 NaN,之后交替 0.7/0.3(明确的持有/空仓)。
    Fake an out-of-sample signal: NaN for the first warmup rows, then alternate 0.7/0.3."""
    vals = np.full(len(index), np.nan)
    for i in range(warmup, len(index)):
        vals[i] = 0.7 if (i // 10) % 2 == 0 else 0.3   # 每 10 天切换一次 | flip every 10 days
    return pd.Series(vals, index=index)


def test_run_ml_backtest_returns_valid_stats():
    """回测能跑通并给出关键指标。| Backtest runs and returns key metrics."""
    _, _, feat_df = build_dataset(make_ohlcv(400, seed=5), horizon=5)
    proba = _proba_from_pattern(feat_df.index)
    bt, stats = run_ml_backtest(feat_df, proba)

    for key in ["Return [%]", "Buy & Hold Return [%]", "Max. Drawdown [%]",
                "Sharpe Ratio", "# Trades"]:
        assert key in stats
    assert stats["# Trades"] >= 1                    # 交替信号必然产生交易 | alternating signal must trade


def test_backtest_too_short_raises():
    """可回测区间太短应报错(拦住无意义的回测)。| Too-short range should raise (guardrail)."""
    _, _, feat_df = build_dataset(make_ohlcv(120, seed=6), horizon=5)
    proba = pd.Series(np.nan, index=feat_df.index)
    proba.iloc[-10:] = 0.6                            # 只有 10 行有信号 | only 10 rows have signal
    try:
        run_ml_backtest(feat_df, proba)
        assert False, "应当因区间太短报错 | should have raised"
    except ValueError:
        pass
