# -*- coding: utf-8 -*-
"""
live.py —— 实时行情源(纯数据,不下单)| real-time quotes (data only, no orders)
=====================================================================
美股实时价来自 Alpaca 免费数据 API(IEX feed)。只读行情,不碰交易。
需要:pip install -e ".[broker]" + 环境变量 ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY
      (在 alpaca.markets 免费注册纸面账户即可拿到,和券商共用同一套 key)。
没 key 或没装库时静默返回空,调用方自动退回 yfinance(延迟)。
"""
from __future__ import annotations

import os

from quantmill import config


def _from_file():
    """从 ~/quant/.alpaca 读 key(双击启动也能用,不必设环境变量)。
    文件两行:ALPACA_API_KEY_ID=xxx / ALPACA_API_SECRET_KEY=yyy"""
    path = os.path.join(config.PROJECT_ROOT, ".alpaca")
    if not os.path.exists(path):
        return None, None
    kv = {}
    try:
        for line in open(path):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                a, b = line.split("=", 1)
                kv[a.strip()] = b.strip()
    except Exception:
        return None, None
    return (kv.get("ALPACA_API_KEY_ID") or kv.get("APCA_API_KEY_ID"),
            kv.get("ALPACA_API_SECRET_KEY") or kv.get("APCA_API_SECRET_KEY"))


def _keys():
    k = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
    s = os.environ.get("ALPACA_API_SECRET_KEY") or os.environ.get("APCA_API_SECRET_KEY")
    if not (k and s):                          # 环境变量没有就读文件 | fall back to file
        fk, fs = _from_file()
        k, s = k or fk, s or fs
    return k, s


def alpaca_available() -> bool:
    """有 key 且装了库 => 可用。| keys present and lib importable."""
    k, s = _keys()
    if not (k and s):
        return False
    try:
        import alpaca  # noqa: F401
        return True
    except Exception:
        return False


def alpaca_last_prices(symbols) -> dict:
    """一次拉多只美股的最新成交价。失败/无 key 返回 {}(调用方退回 yfinance)。
    Latest trade price for many US symbols in one call; {} on any failure."""
    k, s = _keys()
    if not (k and s):
        return {}
    syms = list(dict.fromkeys(symbols))
    if not syms:
        return {}
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
        cli = StockHistoricalDataClient(k, s)
        req = StockLatestTradeRequest(symbol_or_symbols=syms)   # 默认 IEX feed(免费)
        tr = cli.get_stock_latest_trade(req)
        return {sym: float(tr[sym].price) for sym in tr
                if tr.get(sym) is not None and tr[sym].price}
    except Exception:
        return {}
