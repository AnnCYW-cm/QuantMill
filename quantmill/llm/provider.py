# -*- coding: utf-8 -*-
"""
provider.py —— 可插拔情绪打分器 | Pluggable sentiment scorers
=============================================================
把"一批新闻标题"打成情绪分(-1 很负面 ~ +1 很正面)。两条实现:

  AnthropicScorer  真路径:调 Claude(Haiku 4.5),只做"情绪分类"不做"预测涨跌"
                   —— 这是刻意的:分类是有界任务,能降低 LLM 靠"记忆未来"作弊的风险。
  LexiconScorer    离线兜底:金融正负词词典打分(确定性)。明确不是 LLM,只保证流水线能跑/可测。

get_scorer() 有 anthropic 包 + ANTHROPIC_API_KEY 就用 Claude,否则退词典并提示。

⚠️ 铁律:只让模型判断【给定文本】的情绪,绝不喂日期、绝不问"会不会涨"——限制记忆/未来函数。
"""

from __future__ import annotations

import os
import re

# 最新的便宜快模型,足够做标题情绪分类 | latest cheap/fast model, enough for headline sentiment
_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are a financial news sentiment classifier. For each headline about a company, "
    "output a sentiment score from -1.0 (very bad for the company) to 1.0 (very good), "
    "0.0 if neutral or irrelevant. Judge ONLY the tone of the given text. "
    "Do NOT predict stock prices. Return ONLY a JSON array of numbers, one per headline."
)


class LexiconScorer:
    """确定性金融词典打分(离线兜底,非 LLM)。| Deterministic finance-lexicon scorer (offline fallback)."""

    is_llm = False
    name = "lexicon(词典兜底)"

    _POS = {"surge", "beat", "beats", "record", "profit", "growth", "upgrade", "rally",
            "gain", "gains", "soar", "soars", "jump", "jumps", "strong", "boost", "win",
            "wins", "raise", "raised", "outperform", "bullish", "high", "highs", "top"}
    _NEG = {"plunge", "miss", "misses", "loss", "losses", "drop", "drops", "fall", "falls",
            "downgrade", "cut", "cuts", "weak", "warn", "warns", "warning", "lawsuit",
            "probe", "fraud", "slump", "bearish", "low", "lows", "crash", "fear", "fears",
            "recall", "decline", "sink", "sinks", "tumble", "risk", "risks"}

    def score(self, headlines: list[str]) -> list[float]:
        out = []
        for h in headlines:
            words = set(re.findall(r"[a-z']+", (h or "").lower()))
            pos, neg = len(words & self._POS), len(words & self._NEG)
            out.append((pos - neg) / (pos + neg) if (pos + neg) else 0.0)
        return out


class AnthropicScorer:
    """调 Claude 做情绪分类(真 LLM 路径)。| Sentiment via Claude (real LLM path)."""

    is_llm = True
    name = f"Claude({_MODEL})"

    def __init__(self, model: str = _MODEL):
        import anthropic  # 懒加载:没装也不影响其它功能 | lazy import
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()  # 读 ANTHROPIC_API_KEY
        self._model = model

    def score(self, headlines: list[str]) -> list[float]:
        if not headlines:
            return []
        import json
        numbered = "\n".join(f"{i+1}. {h}" for i, h in enumerate(headlines))
        msg = self._client.messages.create(
            model=self._model, max_tokens=512, system=_SYSTEM,
            messages=[{"role": "user", "content": numbered}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r"\[.*\]", text, re.S)
        try:
            arr = json.loads(m.group(0) if m else text)
            scores = [max(-1.0, min(1.0, float(x))) for x in arr]
        except Exception:  # noqa: BLE001  解析失败给中性 | parse fail -> neutral
            scores = [0.0] * len(headlines)
        if len(scores) != len(headlines):        # 数量对不上就补齐 | pad/truncate
            scores = (scores + [0.0] * len(headlines))[:len(headlines)]
        return scores


def get_scorer(prefer_llm: bool = True):
    """自动选打分器:能用 Claude 就用,否则退词典并提示。| Auto-pick scorer."""
    if prefer_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return AnthropicScorer()
        except Exception as e:  # noqa: BLE001
            print(f"[LLM] Claude 不可用({type(e).__name__}),退回词典兜底。"
                  f"装依赖:pip install -e \".[llm]\"")
    elif prefer_llm:
        print("[LLM] 未设 ANTHROPIC_API_KEY,用词典兜底(非 LLM)。"
              "设 key 并 pip install -e \".[llm]\" 后自动改用 Claude。")
    return LexiconScorer()
