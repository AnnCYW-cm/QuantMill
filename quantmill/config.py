# -*- coding: utf-8 -*-
"""
config.py —— 中央配置(所有可调参数的单一来源)
config.py —— Central config (single source of truth for all tunables)
=====================================================================
散落各处的"魔法数字"都收到这里。改一处,全局默认值一起变。
All the scattered "magic numbers" live here. Change one, and the global defaults change.

各函数的默认参数都引用这里的常量;显式传参仍可临时覆盖。
Each function's default arguments reference these constants; passing an explicit
argument still overrides them for that one call.
"""

from __future__ import annotations

import os

# --- 路径 Paths(单一来源,与文件所在层级解耦)| single source, decoupled from file depth ---
# config.py 固定位于 <项目根>/quantmill/config.py,向上两级即项目根。
# config.py always lives at <root>/quantmill/config.py, so two levels up is the project root.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")            # 行情缓存 | market data cache
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")      # 报告/图表产出 | reports & charts
WATCHLIST_PATH = os.path.join(PROJECT_ROOT, "watchlist.txt")  # 自选股清单 | watchlist file
PAPER_PATH = os.path.join(PROJECT_ROOT, "paper_account.json")  # 纸面账户 | paper account state

# --- 数据 Data ---
START = "2018-01-01"          # 默认回测起始日 | default backtest start date
N_SPLITS = 5                  # 时序交叉验证/滚动的折数 | folds for time-series CV / walk-forward

# --- 特征与标注 Features & label ---
HORIZON = 5                   # 预测未来几天涨跌 | predict up/down this many days ahead

# --- 策略与回测 Strategy & backtest ---
BUY_TH = 0.55                 # P(涨) 高于此 -> 持有 | P(up) above this -> hold
SELL_TH = 0.45               # P(涨) 低于此 -> 空仓 | P(up) below this -> go flat
COMMISSION = 0.002           # 单边成本=手续费+滑点 | one-way cost = commission + slippage
CASH = 10_000                # 初始资金 | initial capital

# --- 稳健性检验用的阈值网格 Threshold grid for robustness test ---
ROBUSTNESS_BUY_THS = (0.50, 0.525, 0.55, 0.575, 0.60)
