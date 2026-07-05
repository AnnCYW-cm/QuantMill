# -*- coding: utf-8 -*-
"""test_data.py —— 数据归一化 + 缓存够不够用的判断 | normalization + cache sufficiency"""

import numpy as np
import pandas as pd

from quantmill.data import _normalize, _cache_sufficient, _STD_COLS


def test_normalize_sorts_dedups_and_drops_nan():
    """乱序 + 重复日期 + 缺价行 + 多余列 -> 排序、去重(留最后)、丢缺价、只留标准列。
    Unsorted + duplicate dates + missing-price row + extra columns -> sorted, deduped
    (keep last), drop missing-price rows, keep only standard columns."""
    idx = pd.to_datetime(["2020-01-03", "2020-01-01", "2020-01-02",
                          "2020-01-02", "2020-01-04"])
    df = pd.DataFrame({
        "Open": [3, 1, 2, 2.5, 4], "High": [3, 1, 2, 2.5, 4],
        "Low": [3, 1, 2, 2.5, 4], "Close": [3, 1, 2, 2.5, np.nan],  # 最后一行缺收盘 | last row missing close
        "Volume": [10, 10, 10, 10, 10], "垃圾列": [9, 9, 9, 9, 9],   # 多余列 | extra column
    }, index=idx)

    out = _normalize(df)

    assert list(out.columns) == _STD_COLS               # 只剩标准列 | only standard columns
    assert out.index.is_monotonic_increasing            # 已排序 | sorted
    assert not out.index.duplicated().any()             # 无重复 | no duplicates
    # 2020-01-02 重复,保留最后一条(Close=2.5)| duplicate kept last
    assert out.loc["2020-01-02", "Close"] == 2.5
    # 缺收盘的 2020-01-04 被丢掉 | missing-close row dropped
    assert pd.Timestamp("2020-01-04") not in out.index


def test_normalize_fills_volume_nan_with_zero():
    """成交量缺失填 0(价格缺失才丢行)。| Missing volume -> 0 (only missing price drops the row)."""
    idx = pd.to_datetime(["2020-01-01", "2020-01-02"])
    df = pd.DataFrame({"Open": [1, 2], "High": [1, 2], "Low": [1, 2],
                       "Close": [1, 2], "Volume": [np.nan, 5]}, index=idx)
    out = _normalize(df)
    assert out.loc["2020-01-01", "Volume"] == 0


def test_cache_sufficient_logic():
    """缓存判断:够早且够新才算够用。| Cache is sufficient only if early enough AND fresh enough."""
    idx = pd.bdate_range("2018-01-01", "2026-07-01")
    start, end = pd.Timestamp("2018-01-01"), pd.Timestamp("2026-07-02")

    # 又早又新 -> 都 OK | early and fresh -> both OK
    early_ok, fresh_ok = _cache_sufficient(idx, start, end)
    assert early_ok and fresh_ok

    # 历史不够早(缓存从 2020 起,却要 2018)| not early enough
    idx_late_start = pd.bdate_range("2020-01-01", "2026-07-01")
    early_ok, fresh_ok = _cache_sufficient(idx_late_start, start, end)
    assert not early_ok

    # 数据过期(缓存止于 2023,却要到 2026)| stale
    idx_stale = pd.bdate_range("2018-01-01", "2023-12-29")
    early_ok, fresh_ok = _cache_sufficient(idx_stale, start, end)
    assert early_ok and not fresh_ok
