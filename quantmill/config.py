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


def _env(name: str, default, cast=str):
    """从环境变量 QUANTMILL_<NAME> 读取覆盖值,没有就用默认。| env override, prefixed QUANTMILL_."""
    raw = os.environ.get(f"QUANTMILL_{name}")
    if raw is None:
        return default
    try:
        return cast(raw)
    except (ValueError, TypeError):
        return default


# --- 路径 Paths(单一来源,与文件所在层级解耦)| single source, decoupled from file depth ---
# config.py 固定位于 <项目根>/quantmill/config.py,向上两级即项目根。
# 数据/结果目录可用环境变量 QUANTMILL_DATA_DIR / QUANTMILL_RESULTS_DIR 覆盖(便于容器/多用户)。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = _env("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))        # 行情缓存 | data cache
RESULTS_DIR = _env("RESULTS_DIR", os.path.join(PROJECT_ROOT, "results"))  # 报告产出 | reports
WATCHLIST_PATH = _env("WATCHLIST", os.path.join(PROJECT_ROOT, "watchlist.txt"))  # 自选股清单
PAPER_PATH = _env("PAPER", os.path.join(PROJECT_ROOT, "paper_account.json"))     # 纸面账户

# --- 数据 Data ---(均可用 QUANTMILL_START / QUANTMILL_HORIZON 等覆盖)
START = _env("START", "2018-01-01")               # 默认回测起始日 | default backtest start
N_SPLITS = _env("N_SPLITS", 5, int)               # 时序CV/滚动折数 | CV / walk-forward folds

# --- 特征与标注 Features & label ---
HORIZON = _env("HORIZON", 5, int)                 # 预测未来几天涨跌 | predict N days ahead

# --- 策略与回测 Strategy & backtest ---
BUY_TH = _env("BUY_TH", 0.55, float)              # P(涨) 高于此 -> 持有 | above -> hold
SELL_TH = _env("SELL_TH", 0.45, float)            # P(涨) 低于此 -> 空仓 | below -> flat
COMMISSION = _env("COMMISSION", 0.002, float)     # 单边成本=手续费+滑点 | one-way cost
CASH = _env("CASH", 10_000, float)                # 初始资金 | initial capital

# --- 稳健性检验用的阈值网格 Threshold grid for robustness test ---
ROBUSTNESS_BUY_THS = (0.50, 0.525, 0.55, 0.575, 0.60)
