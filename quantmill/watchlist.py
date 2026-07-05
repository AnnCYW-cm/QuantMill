# -*- coding: utf-8 -*-
"""
watchlist.py —— 自选股清单(用户可编辑)
watchlist.py —— User-editable watchlist
========================================
把"关注哪些票"从代码里搬到一个纯文本文件 watchlist.txt,你随时能改,
不用碰代码。dashboard 和 validate 默认都读它。
Moves "which stocks to watch" out of the code into a plain-text watchlist.txt
you can edit anytime without touching code. dashboard and validate both read it.

文件格式(每行一个:市场 代码;# 开头是注释):
File format (one per line: market code; lines starting with # are comments):
    us AAPL
    hk 00700
    cn 600519
"""

from __future__ import annotations

import logging

import os

from quantmill import config
from quantmill.credibility.validate import DEFAULT_UNIVERSE

# 清单文件放项目根目录 | watchlist file lives at the project root
logger = logging.getLogger(__name__)

WATCHLIST_PATH = config.WATCHLIST_PATH

_VALID_MARKETS = ("us", "hk", "cn")

_TEMPLATE_HEADER = """\
# 我的自选股 · My Watchlist
# 每行一个:市场 代码   (# 开头的行是注释,会被忽略)
# One per line: market code   (lines starting with # are ignored)
# 市场 market: us=美股 US | hk=港股 HK | cn=A股 A-share
# 改完存盘,直接跑 dashboard / validate 就生效。
# Edit, save, then run dashboard / validate — changes take effect immediately.
"""


def _write_default(path: str) -> None:
    """清单不存在时,用默认股票池生成一份带注释的模板。| If missing, create a commented template from the default universe."""
    lines = [_TEMPLATE_HEADER]
    for market, syms in DEFAULT_UNIVERSE.items():
        lines.append(f"\n# --- {market} ---")
        lines.extend(f"{market} {s}" for s in syms)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def load_watchlist(path: str | None = None, create_if_missing: bool = True) -> dict:
    """
    读取自选股清单,返回 {market: [codes]}(保持文件里的顺序)。
    Load the watchlist, return {market: [codes]} (preserving file order).
    文件不存在且 create_if_missing=True 时,自动生成默认模板。
    If the file is missing and create_if_missing=True, auto-generate a default template.
    """
    path = path or WATCHLIST_PATH
    if not os.path.exists(path):
        if create_if_missing:
            _write_default(path)
            logger.info(f"[清单] 未找到,已生成默认自选股清单 -> {os.path.relpath(path)}")
            logger.info("       想改关注的票,直接编辑这个文件即可。")
        else:
            raise FileNotFoundError(path)

    watchlist: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # 支持 "us AAPL" 或 "us:AAPL" 两种写法 | accept "us AAPL" or "us:AAPL"
            parts = line.replace(":", " ").split()
            if len(parts) != 2:
                logger.warning(f"[清单] 第 {lineno} 行格式不对,跳过:{line!r}(应为 '市场 代码')")
                continue
            market, code = parts[0].lower(), parts[1]
            if market not in _VALID_MARKETS:
                logger.warning(f"[清单] 第 {lineno} 行市场无效 {market!r},跳过(应为 us/hk/cn)")
                continue
            watchlist.setdefault(market, []).append(code)

    if not watchlist:
        logger.warning("[清单] 清单是空的,回退到默认股票池。")
        return DEFAULT_UNIVERSE
    total = sum(len(v) for v in watchlist.values())
    logger.info(f"[清单] 已加载 {total} 只:" +
          "  ".join(f"{m}×{len(s)}" for m, s in watchlist.items()))
    return watchlist


if __name__ == "__main__":
    wl = load_watchlist()
    print(wl)
