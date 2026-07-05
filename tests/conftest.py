# -*- coding: utf-8 -*-
"""
conftest.py —— 测试公共夹具 | shared test fixtures
===================================================
所有测试都用【合成的确定性行情】,不联网、可复现。
All tests use synthetic, deterministic OHLCV — no network, fully reproducible.
"""

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n=400, seed=0):
    """造一段带轻微上行漂移 + 噪声的假行情,High/Low 保证合法。
    Build fake OHLCV with slight upward drift + noise; High/Low kept valid."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0004, 0.02, n)          # 日收益 | daily returns
    close = 100 * np.exp(np.cumsum(ret))
    open_ = close * (1 + rng.normal(0, 0.008, n))
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))   # 高 >= 开/收 | high >= open/close
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))    # 低 <= 开/收 | low <= open/close
    vol = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.bdate_range("2015-01-01", periods=n)   # 工作日 | business days
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


@pytest.fixture
def ohlcv():
    """一段 400 天的合成行情。| A 400-day synthetic series."""
    return make_ohlcv(400, seed=0)
