# -*- coding: utf-8 -*-
"""
main.py —— 深挖单只票的入口(薄壳,逻辑在 quantmill/pipeline.py 和 cli.py)
main.py —— Single-stock entry (thin shim; logic lives in quantmill/pipeline.py & cli.py)
=======================================================================================
保留老用法,等价于 `quant analyze`:
Kept for the old usage, equivalent to `quant analyze`:
    ./.venv/bin/python main.py --symbol AAPL --market us
    ./.venv/bin/python main.py --symbol 00700 --market hk

推荐用统一命令 | Prefer the unified command:
    ./.venv/bin/python quant.py analyze AAPL us
"""

from __future__ import annotations

import argparse

from quantmill import config
from quantmill.workflow.pipeline import run_single


def main():
    p = argparse.ArgumentParser(description="深挖单只票 | Deep-dive one stock")
    p.add_argument("--symbol", default="AAPL",
                   help="代码:美股AAPL / A股000001 / 港股00700 | Ticker")
    p.add_argument("--market", default="us", choices=["us", "cn", "hk"])
    p.add_argument("--start", default=config.START)
    p.add_argument("--end", default=None)
    p.add_argument("--horizon", type=int, default=config.HORIZON,
                   help="预测未来几天涨跌 | days ahead to predict")
    p.add_argument("--buy-th", type=float, default=config.BUY_TH, dest="buy_th")
    p.add_argument("--sell-th", type=float, default=config.SELL_TH, dest="sell_th")
    p.add_argument("--cash", type=float, default=config.CASH)
    p.add_argument("--no-cv", action="store_true",
                   help="跳过时序交叉验证(更快) | skip time-series CV")
    a = p.parse_args()

    run_single(a.symbol, a.market, start=a.start, end=a.end, horizon=a.horizon,
               buy_th=a.buy_th, sell_th=a.sell_th, cash=a.cash, do_cv=not a.no_cv)


if __name__ == "__main__":
    main()
