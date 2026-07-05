# -*- coding: utf-8 -*-
"""
test_textfactor.py —— LLM 文本因子(离线,词典路径,含 PIT 锁)
test_textfactor.py —— LLM text factor (offline lexicon path; PIT locked)
"""

import numpy as np
import pandas as pd

from quantmill.llm.textfactor import (combine, cross_text_factor, extract_signals,
                                      text_factor_series)


def test_structured_extraction_signs():
    """词典路径:利好/利空/风险 三维方向正确。"""
    sigs = extract_signals([
        "公司业绩超预期,上调全年指引",     # 正面 + 指引上调
        "遭证监会立案调查,面临退市风险",   # 风险
        "今日召开股东大会",                # 中性
    ], prefer_llm=False)
    assert sigs[0]["outlook"] > 0 and sigs[0]["guidance"] == 1
    assert sigs[1]["risk"] > 0
    assert sigs[2]["outlook"] == 0 and sigs[2]["guidance"] == 0
    # 组合:正面前瞻 > 中性 > 风险
    assert combine(sigs[0]) > combine(sigs[2]) > combine(sigs[1])


def test_pit_no_lookahead():
    """★ 严格 PIT:一条未来发布的新闻,绝不能影响它发布前的因子值。"""
    idx = pd.bdate_range("2024-01-01", periods=10)
    news_day = idx[6]
    recs = [{"time": pd.Timestamp(news_day), "score": 1.0}]
    f = text_factor_series(recs, idx, halflife=5)
    assert f.iloc[:6].isna().all()          # 发布前:全 NaN(没偷看未来)
    assert not np.isnan(f.iloc[6])          # 发布当天起:有值
    assert f.iloc[6] > 0


def test_cross_text_factor_shape():
    """整池 → (date, symbol) 因子,口径与 cross 面板一致。"""
    idx = pd.bdate_range("2024-01-01", periods=5)
    panel_index = [(d, s) for d in idx for s in ("AAA", "BBB")]
    news = {"AAA": [{"title": "利好 超预期", "time": pd.Timestamp(idx[1])}],
            "BBB": [{"title": "立案调查 退市风险", "time": pd.Timestamp(idx[0])}]}
    f = cross_text_factor(news, panel_index, halflife=5, prefer_llm=False)
    assert list(f.index.names) == ["date", "symbol"]
    assert len(f) == len(panel_index)
    # BBB(风险)最后一天 应低于 AAA(利好)
    assert f.loc[(idx[-1], "BBB")] < f.loc[(idx[-1], "AAA")]
