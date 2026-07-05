"""
rules.py —— 各市场交易制度 | Per-market trading rules
======================================================
让回测贴近真实成交,而不是"纸面理想"。

  涨跌停 price_limit  A股主板 ±10%:锁死的票当日不可成交(回测里冻结其仓位)
  卖出成本 sell_cost  A股卖出印花税 0.05%(2023 后单边)+ 港股印花税
  T+1                A股当日买入不可当日卖出;本回测按 rebalance≥1 天持有,天然满足

⚠️ 这些是"够用"的近似(未建模:开盘即封 vs 盘中触及、ST股 ±5%、创业板/科创板 ±20%、
   最低佣金、过户费)。够让 A股回测不至于严重高估,精确化留待后续。
"""

from __future__ import annotations

# market -> {price_limit(涨跌停幅度), sell_cost(卖出额外成本), t_plus(几日后可卖)}
MARKET_RULES = {
    "us": {"price_limit": None, "sell_cost": 0.0, "t_plus": 0},
    "hk": {"price_limit": None, "sell_cost": 0.0010, "t_plus": 0},   # 港股印花税约0.1%卖出
    "cn": {"price_limit": 0.10, "sell_cost": 0.0005, "t_plus": 1},   # A股±10%,印花税0.05%,T+1
}


def market_rules(market: str) -> dict:
    """取某市场的交易制度;未知市场退化为美股(无限制)。| Get market rules; default to US."""
    return MARKET_RULES.get(market.lower(), MARKET_RULES["us"])
