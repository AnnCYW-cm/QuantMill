# -*- coding: utf-8 -*-
"""
test_llm.py —— 情绪打分器 + PIT 情绪因子的正确性(重点:无未来函数)
test_llm.py —— Sentiment scorer + PIT feature correctness (above all: NO look-ahead)
====================================================================================
"""

import numpy as np
import pandas as pd

from quantmill.llm.provider import LexiconScorer
from quantmill.llm.sentiment import score_headlines, sentiment_feature


class _MockScorer:
    """测试用:标题里带 'good' 记 +1,'bad' 记 -1,否则 0。| deterministic mock LLM."""
    name = "mock"
    is_llm = True

    def score(self, headlines):
        return [1.0 if "good" in h else (-1.0 if "bad" in h else 0.0) for h in headlines]


# ---------------------------------------------------------------- 打分器 | scorers
def test_lexicon_scorer_direction():
    """词典打分:利好>0,利空<0,中性=0。| Lexicon: positive>0, negative<0, neutral=0."""
    sc = LexiconScorer()
    a, b, c = sc.score(["Company beats record profit and surges",
                         "Firm plunge on fraud probe and lawsuit",
                         "Company announces annual meeting date"])
    assert a > 0 and b < 0 and c == 0.0


def test_lexicon_deterministic():
    """同输入同输出(确定性)。| Deterministic."""
    sc = LexiconScorer()
    h = ["Stock surges to record high", "Shares plunge on weak guidance"]
    assert sc.score(h) == sc.score(h)


def test_score_headlines_with_injected_scorer():
    """score_headlines 用注入的打分器。| score_headlines uses injected scorer."""
    out = score_headlines(["this is good", "this is bad", "meh"], scorer=_MockScorer())
    assert out == [1.0, -1.0, 0.0]


# ---------------------------------------------------------------- PIT 情绪因子 | PIT feature
def _news(day, s):
    return {"time": pd.Timestamp(day, tz="UTC"), "sentiment": s}


def test_sentiment_feature_pit_basic():
    """第 t 天只聚合 t 及之前的新闻;之前无新闻则 NaN。| Only news on/before t; NaN if none prior."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    news = [_news("2020-01-03", 1.0), _news("2020-01-07", -1.0)]
    f = sentiment_feature(news, idx, halflife=5)
    assert np.isnan(f["2020-01-01"]) and np.isnan(f["2020-01-02"])  # 之前无新闻
    assert abs(f["2020-01-03"] - 1.0) < 1e-9        # 只有 +1 那条 -> 1.0
    assert abs(f["2020-01-06"] - 1.0) < 1e-9        # 仍只有 +1 那条(单条加权均值=其值)
    assert f["2020-01-07"] < 1.0                     # 加入 -1 -> 下降


def test_sentiment_feature_no_lookahead():
    """★核心★ 加入【未来】发布的新闻,不改变【过去】的因子值。
    ★CORE★ Adding future-dated news must not change past feature values."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    news = [_news("2020-01-03", 1.0), _news("2020-01-07", -1.0)]
    f1 = sentiment_feature(news, idx, halflife=5)
    news2 = news + [_news("2020-01-20", 1.0)]        # 区间之后发布 | published after the window
    f2 = sentiment_feature(news2, idx, halflife=5)
    assert np.allclose(f1.to_numpy(), f2.to_numpy(), equal_nan=True)


def test_sentiment_feature_decay_blend():
    """两条新闻衰减混合:结果在两者之间。| Decayed blend of two news lies between them."""
    idx = pd.date_range("2020-01-01", periods=12, freq="D")
    news = [_news("2020-01-03", 1.0), _news("2020-01-05", -1.0)]
    f = sentiment_feature(news, idx, halflife=3)
    assert -1.0 <= f["2020-01-10"] <= 1.0            # 混合值在 [-1,1]
    assert np.isnan(f["2020-01-02"])                  # 首条之前 NaN
