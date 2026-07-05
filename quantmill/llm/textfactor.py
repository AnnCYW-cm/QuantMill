# -*- coding: utf-8 -*-
"""
textfactor.py —— LLM 文本 → 结构化因子 | LLM text → structured cross-sectional factor
=====================================================================
比标量情绪(sentiment.py)更深一层:让 LLM 从文本【分类抽取】三维结构化信号,
再严格 PIT 聚合成横截面因子,接进 cross 的 IC/可信度框架。

★ 抽取的是"文本说了什么"(分类),不是"股票会不会涨"(预测)——
  这是防 LLM 用记忆里的未来作弊的关键纪律(与 sentiment.py 一致)。

三维信号(每条文本):
  outlook   前瞻语气   −1(明确利空) … +1(明确利好),仅据文本内容
  guidance  指引变化   +1 上调 / −1 下调 / 0 未提
  risk      风险旗标    0 无 … 1 重大(诉讼/立案/债务/监管)
组合因子 = outlook + 0.5·guidance − risk(越大=文本越正面前瞻)

无 ANTHROPIC_API_KEY 时退化为词典启发式(同样的三维输出,可离线跑/测)。
免费源无历史新闻 → 该因子 alpha 暂不能回测,只能前瞻使用 + 过可信度层。
"""
from __future__ import annotations

import json
import math
import re

import pandas as pd

from quantmill.llm import llm_client

_PROMPT = """你是金融文本标注员。对每条中/英文标题,仅根据文本【陈述的内容】(不要预测股价、\
不要用你的先验知识猜未来)输出三个字段:
- outlook: 该文本对公司前景的语气,-1(明确负面)到 1(明确正面),0 中性
- guidance: 文本是否提到上调/下调业绩指引或预测,1=上调 -1=下调 0=未提
- risk: 文本是否点出重大风险(诉讼/立案/造假/债务/监管处罚),0=无 到 1=严重
只返回一个 JSON 数组,每条标题一个对象,顺序与输入一致,不要多余文字。
标题:
{items}"""

# 词典兜底关键词 | lexicon fallback keywords
_POS = ["上涨", "增长", "利好", "超预期", "回购", "中标", "盈利", "创新高", "beat", "surge",
        "record", "raise", "upgrade", "strong", "profit"]
_NEG = ["下跌", "下滑", "亏损", "减持", "低于预期", "暴跌", "miss", "cut", "downgrade", "loss", "plunge"]
_GUID_UP = ["上调", "调高", "raise", "raised", "guidance up", "beat"]
_GUID_DN = ["下调", "调低", "预亏", "warn", "cut", "lower"]
_RISK = ["诉讼", "立案", "调查", "造假", "违规", "处罚", "债务", "退市", "商誉", "probe",
         "lawsuit", "fraud", "investigation", "default", "delist", "sued"]


def _lexicon_extract(texts: list[str]) -> list[dict]:
    out = []
    for t in texts:
        s = str(t)
        low = s.lower()
        pos = sum(w in s or w in low for w in _POS)
        neg = sum(w in s or w in low for w in _NEG)
        outlook = 0.0 if pos + neg == 0 else max(-1.0, min(1.0, (pos - neg) / (pos + neg)))
        guidance = (1 if any(w in s or w in low for w in _GUID_UP) else 0) \
            - (1 if any(w in s or w in low for w in _GUID_DN) else 0)
        risk = min(1.0, 0.5 * sum(w in s or w in low for w in _RISK))
        out.append({"outlook": round(outlook, 3), "guidance": int(guidance), "risk": round(risk, 3)})
    return out


def _llm_extract(texts: list[str]) -> list[dict] | None:
    """走可插拔 LLM(DeepSeek/Qwen/Gemini/本地Ollama/Claude,见 llm_client)做结构化抽取。
    没配置或失败返回 None(调用方退词典)。"""
    items = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    raw = llm_client.chat(_PROMPT.format(items=items), max_tokens=1024, temperature=0.0)
    if not raw:
        return None
    try:
        arr = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
        out = [{"outlook": float(d.get("outlook", 0)),
                "guidance": int(d.get("guidance", 0)),
                "risk": float(d.get("risk", 0))} for d in arr[:len(texts)]]
        return out if len(out) == len(texts) else None
    except Exception:  # noqa: BLE001
        return None


def extract_signals(texts: list[str], prefer_llm: bool = True) -> list[dict]:
    """一批文本 → 每条的三维结构化信号。有 Claude key 用 LLM,否则词典兜底。"""
    if not texts:
        return []
    if prefer_llm:
        r = _llm_extract(texts)
        if r is not None:
            return r
    return _lexicon_extract(texts)


def combine(sig: dict) -> float:
    """三维 → 单值文本因子。| structured signal -> scalar factor value."""
    return float(sig["outlook"]) + 0.5 * float(sig["guidance"]) - float(sig["risk"])


def text_factor_series(records: list[dict], trading_index, halflife: float = 5.0) -> pd.Series:
    """严格 PIT:第 t 天只聚合【发布日 ≤ t】的文本因子,按 (t−发布日) 指数衰减加权。
    records: [{time: Timestamp(带时区), score: float}]。返回按 trading_index 的因子序列。"""
    idx = pd.DatetimeIndex(trading_index)
    recs = [r for r in records if r.get("time") is not None]
    if not recs:
        return pd.Series(index=idx, dtype=float)
    rt = pd.to_datetime([r["time"] for r in recs]).tz_localize(None)
    rs = pd.Series([r["score"] for r in recs], index=rt).sort_index()
    lam = math.log(2) / max(1e-9, halflife)
    out = []
    for t in idx:
        past = rs[rs.index <= t]                       # ★ PIT:只用已发布
        if len(past) == 0:
            out.append(float("nan")); continue
        w = pd.Series([math.exp(-lam * (t - d).days) for d in past.index], index=past.index)
        out.append(float((past * w).sum() / w.sum()))
    return pd.Series(out, index=idx)


def cross_text_factor(news_by_symbol: dict, panel_index, halflife: float = 5.0,
                      prefer_llm: bool = True) -> pd.Series:
    """整个股票池的文本因子,返回与 panel_index 对齐的 (date, symbol) 因子。
    news_by_symbol: {symbol: [{title, time}, ...]}。复用 cross 的 (date,symbol) 面板口径。"""
    dates = pd.DatetimeIndex(sorted({d for d, _ in panel_index})).tz_localize(None)
    blocks = {}
    for sym, items in news_by_symbol.items():
        titles = [it["title"] for it in items]
        sigs = extract_signals(titles, prefer_llm=prefer_llm)
        recs = [{"time": it["time"], "score": combine(s)} for it, s in zip(items, sigs)]
        blocks[sym] = text_factor_series(recs, dates, halflife)
    long = []
    for (d, s) in panel_index:
        v = blocks.get(s)
        long.append(float(v.get(pd.Timestamp(d).tz_localize(None), float("nan"))) if v is not None else float("nan"))
    return pd.Series(long, index=pd.MultiIndex.from_tuples(list(panel_index), names=["date", "symbol"]))
