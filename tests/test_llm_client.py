# -*- coding: utf-8 -*-
"""
test_llm_client.py —— 可插拔 LLM 客户端(OpenAI 兼容),用本地 mock 端点真跑一遍
test_llm_client.py —— pluggable OpenAI-compatible client, exercised against a local mock
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from quantmill.llm import llm_client
from quantmill.llm.textfactor import extract_signals

_ENV = ("QUANTMILL_LLM_BASE_URL", "QUANTMILL_LLM_MODEL", "QUANTMILL_LLM_KEY",
        "OPENAI_BASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


def _clear(mp):
    for k in _ENV:
        mp.delenv(k, raising=False)


class _Handler(BaseHTTPRequestHandler):
    reply = "hello"

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)                                  # 读掉请求体
        body = json.dumps({"choices": [{"message": {"content": self.reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):                              # 静音
        pass


@pytest.fixture
def mock_server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def test_backend_label_from_env(monkeypatch):
    _clear(monkeypatch)
    assert llm_client.backend() is None                     # 没配 → None(退词典)
    monkeypatch.setenv("QUANTMILL_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("QUANTMILL_LLM_MODEL", "deepseek-chat")
    assert llm_client.backend() == "api.deepseek.com(deepseek-chat)"


def test_chat_graceful_when_unconfigured(monkeypatch):
    _clear(monkeypatch)
    assert llm_client.chat("hi") is None                    # 没配 → None,不抛异常


def test_chat_hits_openai_compatible_endpoint(monkeypatch, mock_server):
    _clear(monkeypatch)
    port = mock_server.server_address[1]
    monkeypatch.setenv("QUANTMILL_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("QUANTMILL_LLM_MODEL", "mock-model")
    monkeypatch.setenv("QUANTMILL_LLM_KEY", "x")
    _Handler.reply = "pong"
    assert llm_client.chat("ping") == "pong"                # 真发 HTTP、真解析


def test_extract_signals_uses_llm_when_configured(monkeypatch, mock_server):
    """配了 LLM 端点时,extract_signals 走 LLM 解析其 JSON(而非词典)。"""
    _clear(monkeypatch)
    port = mock_server.server_address[1]
    monkeypatch.setenv("QUANTMILL_LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("QUANTMILL_LLM_MODEL", "mock-model")
    _Handler.reply = '[{"outlook": 0.9, "guidance": 1, "risk": 0.0}]'
    sig = extract_signals(["随便一条标题"], prefer_llm=True)
    assert sig == [{"outlook": 0.9, "guidance": 1, "risk": 0.0}]
