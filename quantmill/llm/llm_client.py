# -*- coding: utf-8 -*-
"""
llm_client.py —— 可插拔 LLM 客户端 | pluggable LLM client (OpenAI-compatible)
=====================================================================
一个接口,想用哪家/本地任选——改环境变量就行,不改代码,也不锁死在贵的 Claude 上。
绝大多数便宜/免费方案都支持 OpenAI 兼容接口:DeepSeek、通义千问(DashScope 兼容模式)、
Gemini(OpenAI 兼容端点)、本地 Ollama、Groq、OpenAI……

配置(环境变量)| config via env:
    QUANTMILL_LLM_BASE_URL   OpenAI 兼容端点(到 /v1)
    QUANTMILL_LLM_MODEL      模型名
    QUANTMILL_LLM_KEY        API key(本地 Ollama 随便填)
  例:
    DeepSeek : BASE_URL=https://api.deepseek.com/v1        MODEL=deepseek-chat
    通义千问 : BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  MODEL=qwen-turbo
    Gemini  : BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai  MODEL=gemini-2.5-flash-lite
    本地Ollama: BASE_URL=http://localhost:11434/v1          MODEL=qwen3:4b   KEY=ollama
  也兼容 OPENAI_BASE_URL / OPENAI_API_KEY;或退回 ANTHROPIC_API_KEY 走 Claude。
都没配 → chat() 返回 None,调用方退词典兜底(离线)。
"""
from __future__ import annotations

import json
import os
import urllib.request

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _cfg():
    base = os.environ.get("QUANTMILL_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model = os.environ.get("QUANTMILL_LLM_MODEL")
    key = os.environ.get("QUANTMILL_LLM_KEY") or os.environ.get("OPENAI_API_KEY")
    return base, model, key


def backend() -> str | None:
    """当前 LLM 后端标签(如 'api.deepseek.com(deepseek-chat)');没配置返回 None。"""
    base, model, _ = _cfg()
    if base and model:
        host = base.split("//")[-1].split("/")[0]
        return f"{host}({model})"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return f"Claude({_ANTHROPIC_MODEL})"
    return None


def chat(prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> str | None:
    """发一条 user 消息,返回助手文本。没配置或失败返回 None(调用方退词典)。"""
    base, model, key = _cfg()
    if base and model:
        return _openai_compat(base, model, key, prompt, max_tokens, temperature)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _anthropic(prompt, max_tokens, temperature)
    return None


def _openai_compat(base, model, key, prompt, max_tokens, temperature):
    url = base.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key or 'ollama'}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read())
        return d["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return None


def _anthropic(prompt, max_tokens, temperature):
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        m = c.messages.create(model=_ANTHROPIC_MODEL, max_tokens=max_tokens,
                              temperature=temperature,
                              messages=[{"role": "user", "content": prompt}])
        return m.content[0].text
    except Exception:  # noqa: BLE001
        return None
