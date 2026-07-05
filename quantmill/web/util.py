# -*- coding: utf-8 -*-
"""
util.py —— 请求参数校验 | request-arg validation
=====================================================================
非法 market / 空 symbol 直接 400(由全局错误处理器转成 JSON),
避免把脏输入喂给 yfinance/akshare 后崩成 500。
"""
from __future__ import annotations

from flask import abort, request

_MARKETS = ("us", "hk", "cn")


def get_market(default: str = "us") -> str:
    m = request.args.get("market", default)
    if m not in _MARKETS:
        abort(400, description=f"invalid market {m!r} (use us/hk/cn)")
    return m


def get_symbol() -> str:
    s = (request.args.get("symbol") or "").strip()
    if not s:
        abort(400, description="missing 'symbol'")
    return s
