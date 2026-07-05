# -*- coding: utf-8 -*-
"""
news.py —— 新闻抓取 | News fetching
====================================
从 yfinance 抓某只股票的近期新闻(标题 + 发布时间)。健壮解析其多变的 schema。

⚠️ 现实约束:免费源(yahoo)只有【近期】少量新闻,没有深度历史。
   所以 LLM 情绪因子的【历史回测】暂时做不了——本模块诚实地只提供"近期新闻"。
   Free sources only give recent news, no deep history -> can't yet backtest the sentiment factor.
"""

from __future__ import annotations

import pandas as pd

from quantmill.data import _cn_to_yahoo, _hk_to_yahoo


def _to_yahoo(symbol: str, market: str) -> str:
    market = market.lower()
    if market == "hk":
        return _hk_to_yahoo(symbol)
    if market == "cn":
        return _cn_to_yahoo(symbol)
    return symbol


def fetch_news(symbol: str, market: str = "us", limit: int = 20) -> list[dict]:
    """
    抓近期新闻,返回 [{title, time(带时区 Timestamp 或 None)}]。
    Fetch recent news -> [{title, time}]. Robust to yfinance's changing schema.
    """
    import yfinance as yf

    try:
        raw = yf.Ticker(_to_yahoo(symbol, market)).news or []
    except Exception:  # noqa: BLE001
        raw = []

    items = []
    for it in raw[:limit]:
        c = it.get("content", it) if isinstance(it, dict) else {}
        title = c.get("title") or it.get("title")
        if not title:
            continue
        ts = None
        for key in ("pubDate", "displayTime"):        # 新 schema | new schema
            if c.get(key):
                ts = pd.to_datetime(c[key], utc=True, errors="coerce")
                break
        if ts is None and it.get("providerPublishTime"):  # 旧 schema | old schema
            ts = pd.to_datetime(it["providerPublishTime"], unit="s", utc=True)
        items.append({"title": title, "time": None if pd.isna(ts) else ts})
    return items
