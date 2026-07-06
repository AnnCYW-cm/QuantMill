# -*- coding: utf-8 -*-
"""前瞻纸面记录测试 —— 焊死"只前进、不回看"的纪律(离线,纯状态推进)。"""
import numpy as np
import pandas as pd

from quantmill.paper.forward import (forward_summary, step_forward,
                                     target_weights)


def _prices(base, mult):
    return {s: base[s] * m for s, m in zip(base, mult)}


def test_init_build():
    base = {"A": 10.0, "B": 20.0, "C": 30.0}
    tgt = {"A": 0.4, "B": 0.35, "C": 0.25}
    st = step_forward({}, tgt, base, "2026-01-01", notional=100000.0)
    assert st["inception"] == "2026-01-01"
    assert len(st["nav"]) == 1 and st["nav"][0]["nav"] == 100000.0
    assert st["positions"] == tgt and st["exposure"] == 1.0


def test_mark_to_market_moves_nav():
    base = {"A": 10.0, "B": 20.0}
    tgt = {"A": 0.5, "B": 0.5}
    st = step_forward({}, tgt, base, "2026-01-01")
    # 两只都涨 10% → 组合 +10%
    st = step_forward(st, tgt, _prices(base, [1.1, 1.1]), "2026-01-02", horizon=20)
    assert len(st["nav"]) == 2
    assert abs(st["nav"][-1]["nav"] - 110000.0) < 1.0


def test_append_only_never_rewrites_history():
    """核心纪律:历史净值点一旦写下,后续任何一步都不得改动。"""
    base = {"A": 10.0, "B": 20.0}
    tgt = {"A": 0.5, "B": 0.5}
    st = step_forward({}, tgt, base, "2026-01-01")
    st = step_forward(st, tgt, _prices(base, [1.2, 0.9]), "2026-01-02", horizon=20)
    snapshot = [dict(p) for p in st["nav"]]           # 记下前两点
    # 再推进多步,历史前缀必须逐字不变
    for i, day in enumerate(["2026-01-03", "2026-01-05", "2026-01-09"]):
        st = step_forward(st, tgt, _prices(base, [1.0 + 0.01 * i, 1.0]), day, horizon=20)
        assert st["nav"][:2] == snapshot                # 前缀绝不改写
    assert len(st["nav"]) == 5                          # 每个新日期恰好追加一点


def test_same_day_updates_not_appends():
    """同一天重复跑 = 更新今天,不新增点、不动历史。"""
    base = {"A": 10.0}
    tgt = {"A": 1.0}
    st = step_forward({}, tgt, base, "2026-01-01")
    st = step_forward(st, tgt, {"A": 11.0}, "2026-01-02", horizon=20)
    n = len(st["nav"])
    st = step_forward(st, tgt, {"A": 12.0}, "2026-01-02", horizon=20)   # 同一天再跑
    assert len(st["nav"]) == n                          # 没有新增
    assert abs(st["nav"][-1]["nav"] - 120000.0) < 1.0   # 今天被更新为最新价


def test_rebalance_only_after_horizon():
    base = {"A": 10.0, "B": 20.0}
    tgt1 = {"A": 0.5, "B": 0.5}
    tgt2 = {"A": 0.2, "B": 0.8}
    st = step_forward({}, tgt1, base, "2026-01-01")
    st = step_forward(st, tgt2, base, "2026-01-10", horizon=20)   # 未满 horizon
    assert st["positions"] == tgt1                                # 不换
    st = step_forward(st, tgt2, base, "2026-02-05", horizon=20)   # 超过 20 天
    assert st["positions"] == tgt2                                # 才换


def test_drawdown_switch_derisks():
    """跌破回撤阈值 → 换仓时敞口自动降到 derisk。"""
    base = {"A": 10.0}
    tgt = {"A": 1.0}
    st = step_forward({}, tgt, base, "2026-01-01", dd_limit=0.12)
    # 中途暴跌 20%(标记市值),再到换仓日
    st = step_forward(st, tgt, {"A": 8.0}, "2026-01-10", horizon=20, dd_limit=0.12)
    st = step_forward(st, tgt, {"A": 8.0}, "2026-02-05", horizon=20, dd_limit=0.12, derisk=0.5)
    assert st["exposure"] == 0.5                                  # 已降仓


def test_target_weights_from_panel():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    syms = [f"S{i}" for i in range(6)]
    idx = pd.MultiIndex.from_product([dates, syms], names=["date", "symbol"])
    panel = pd.DataFrame({"vol_20d": np.linspace(0.1, 0.3, len(idx))}, index=idx)
    score = pd.Series(np.tile([5, 4, 3, 2, 1, 0], 3), index=idx, dtype=float)
    w = target_weights(panel, score, k=3, max_weight=0.6)
    assert len(w) == 2 or len(w) == 3        # k 被 n_uni//3 收窄
    assert abs(sum(w.values()) - 1.0) < 1e-6 # 权重归一


def test_summary_shape():
    base = {"A": 10.0}
    st = step_forward({}, {"A": 1.0}, base, "2026-01-01")
    st = step_forward(st, {"A": 1.0}, {"A": 11.0}, "2026-01-02", horizon=20)
    s = forward_summary(st)
    assert s["points"] == 2 and s["return%"] > 0
