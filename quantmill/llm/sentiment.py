# -*- coding: utf-8 -*-
"""
sentiment.py —— 新闻 → 情绪 → PIT 特征 | News → sentiment → point-in-time feature
=================================================================================
  score_headlines    一批标题 → 情绪分(-1~1),用 provider 里的打分器
  news_sentiment     抓某股近期新闻 + 打分 → 当前情绪(均值 + 每条明细),给"今日信号"用
  sentiment_feature  ★ 严格 PIT 情绪因子:第 t 天只聚合【t 当天及之前发布】的新闻(时间指数衰减)

⚠️ 头号铁律(呼应调研的"记忆/未来函数"警告):
   sentiment_feature 在第 t 天绝不使用未来发布的新闻。由 tests/test_llm.py 锁死。
   任何 LLM 情绪因子在被信任前,必须过可信度层(DSR/PBO/广度)。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def score_headlines(headlines, scorer=None) -> list[float]:
    """一批标题 → 情绪分。scorer 缺省时自动选(Claude 或词典)。| Headlines -> sentiment scores."""
    from quantmill.llm.provider import get_scorer
    scorer = scorer or get_scorer()
    return scorer.score(list(headlines))


def news_sentiment(symbol: str, market: str = "us", scorer=None,
                   limit: int = 15) -> dict:
    """
    某股近期新闻的当前情绪:抓新闻 → 打分 → 返回 {mean, n, scorer, items}。
    Current sentiment from a stock's recent news (for the 'today' signal).
    """
    from quantmill.llm.news import fetch_news
    from quantmill.llm.provider import get_scorer
    scorer = scorer or get_scorer()
    items = fetch_news(symbol, market, limit=limit)
    scores = scorer.score([it["title"] for it in items])
    for it, s in zip(items, scores):
        it["sentiment"] = s
    return {"mean": float(np.mean(scores)) if scores else 0.0,
            "n": len(items), "scorer": scorer.name, "items": items}


def sentiment_feature(news_items, trading_index, halflife: float = 5.0,
                      fillna=None) -> pd.Series:
    """
    ★ 严格 point-in-time 情绪因子。第 t 天只聚合【发布日 ≤ t】的新闻,按 (t-发布日) 指数衰减加权。
    ★ Strict PIT sentiment feature: at day t, aggregate only news published on/before t, time-decayed.

    参数 / Args:
        news_items    : [{time: 带时区 Timestamp, sentiment: float}]
        trading_index : 交易日 DatetimeIndex | trading-day index
        halflife      : 情绪半衰期(天)| sentiment half-life in days
        fillna        : 无历史新闻的日子填什么(None=保留 NaN)| fill value for days with no prior news

    返回 index=trading_index 的情绪 Series。绝不使用未来新闻。
    """
    events = sorted(
        (pd.Timestamp(it["time"]).tz_localize(None).normalize(), float(it["sentiment"]))
        for it in news_items if it.get("time") is not None
        and it.get("sentiment") is not None
    )
    out = pd.Series(index=trading_index, dtype=float)
    for t in trading_index:
        tt = pd.Timestamp(t).tz_localize(None).normalize()
        num = den = 0.0
        for d, s in events:
            if d > tt:                       # 已排序,后面都比 t 晚 -> 停(不看未来)
                break
            w = 0.5 ** (max((tt - d).days, 0) / halflife)
            num += w * s
            den += w
        out[t] = num / den if den > 0 else np.nan
    return out if fillna is None else out.fillna(fillna)
