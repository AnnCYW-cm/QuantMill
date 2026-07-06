# -*- coding: utf-8 -*-
"""严格 PIT 对齐测试 —— 焊死"披露滞后不泄露未来"(离线)。"""
import numpy as np
import pandas as pd

from quantmill.cross.panel import _pit_align


def test_pit_respects_availability_lag():
    """财报数据日 3/31,但 4/30 才公开。交易日 4/15 只能是 NaN,不能提前看到。"""
    days = pd.date_range("2023-03-25", "2023-05-10", freq="B")
    v = pd.DataFrame(
        {"pe": [20.0], "available_date": pd.to_datetime(["2023-04-30"])},
        index=pd.to_datetime(["2023-03-31"]),      # 数据对应 3/31,但 4/30 才可知
    )
    out = _pit_align(v, days)
    assert np.isnan(out.loc["2023-04-14", "pe"])   # 公开前:看不到(否则=未来函数)
    assert np.isnan(out.loc["2023-04-28", "pe"])   # 公开前一日:仍看不到
    assert out.loc["2023-05-02", "pe"] == 20.0     # 公开后:才用上


def test_pit_uses_latest_available_row():
    """两期财报,取交易日当天已公开的【最新】一期。"""
    days = pd.date_range("2023-01-02", "2023-09-01", freq="B")
    v = pd.DataFrame(
        {"pe": [10.0, 12.0],
         "available_date": pd.to_datetime(["2023-01-31", "2023-04-30"])},
        index=pd.to_datetime(["2022-12-31", "2023-03-31"]),
    )
    out = _pit_align(v, days)
    assert out.loc["2023-03-01", "pe"] == 10.0     # 只公开了第一期
    assert out.loc["2023-06-01", "pe"] == 12.0     # 第二期已公开,用最新


def test_pit_without_available_date_falls_back():
    """无 available_date(老缓存)→ 退化 reindex+ffill,与原行为一致。"""
    days = pd.date_range("2023-01-02", "2023-01-10", freq="B")
    v = pd.DataFrame({"pe": [10.0, 11.0]}, index=pd.to_datetime(["2023-01-03", "2023-01-05"]))
    out = _pit_align(v, days)
    assert out.loc["2023-01-04", "pe"] == 10.0     # ffill 自 1/3
    assert out.loc["2023-01-06", "pe"] == 11.0
    assert out.index.equals(days)                  # 索引对齐到交易日
