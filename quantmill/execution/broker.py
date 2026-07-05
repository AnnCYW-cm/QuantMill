# -*- coding: utf-8 -*-
"""
broker.py —— 券商抽象 + 本地纸面账户 + Alpaca 适配器
broker.py —— Broker abstraction + local paper account + Alpaca adapter
======================================================================
把"下单/持仓/估值"抽象成 Broker 接口,一套引擎驱动多种券商:

  Broker        接口 | interface
  PaperBroker   本地纸面账户(JSON 持久化,整股成交)| local paper account
  AlpacaBroker  真券商:Alpaca 美股(默认纸面端点,需密钥)| real broker: Alpaca US

"目标权重 → 订单"的纯逻辑 compute_orders 两者共用,已单测。
The pure "target weights -> orders" logic (compute_orders) is shared and unit-tested.
"""

from __future__ import annotations

import json
import math
import os

from quantmill import config


# ---------------------------------------------------------------- 纯逻辑 | pure logic
def compute_orders(target_weights: dict, prices: dict, equity: float,
                   positions: dict, lot: int = 1,
                   allow_fractional: bool = False) -> dict:
    """
    由目标权重 + 现价 + 总权益 + 当前持仓,算出要下的订单 {symbol: 股数(正买负卖)}。
    Compute orders {symbol: delta_qty} from target weights + prices + equity + positions.
    目标里没有的持仓 -> 清仓(delta = -当前)。整股(lot)或允许小数股。
    """
    tol = 1e-6 if allow_fractional else 1e-9
    targets = {}
    for s, wt in target_weights.items():
        if s not in prices or prices[s] <= 0:
            continue
        raw = wt * equity / prices[s]
        targets[s] = round(raw, 4) if allow_fractional else math.floor(raw / lot) * lot

    orders = {}
    for s in set(targets) | set(positions):
        if s not in prices:                      # 缺价的持仓动不了 | can't trade w/o price
            continue
        delta = targets.get(s, 0.0) - positions.get(s, 0.0)
        if abs(delta) > tol:
            orders[s] = delta
    return orders


# ---------------------------------------------------------------- 接口 | interface
class Broker:
    """券商接口。| Broker interface. 子类必须实现 value/positions/rebalance_to。"""

    def value(self, prices: dict | None = None) -> float:
        raise NotImplementedError

    def positions(self) -> dict:
        raise NotImplementedError

    def rebalance_to(self, target_weights: dict, prices: dict, **kw) -> dict:
        raise NotImplementedError

    # 可选:本地账户才需要落盘;真券商状态在券商侧,这里 no-op
    def record(self, prices: dict, when: str | None = None) -> None:
        pass

    def save(self) -> None:
        pass


# ---------------------------------------------------------------- 本地纸面 | paper
class PaperBroker(Broker):
    """本地纸面账户,状态持久化到 JSON。| Local paper account persisted to JSON."""

    def __init__(self, path: str | None = None, init_cash: float = 100_000.0):
        self.path = path or config.PAPER_PATH
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                st = json.load(f)
        else:
            st = {"cash": init_cash, "init_cash": init_cash,
                  "positions": {}, "history": [], "trades": []}
        self.cash = float(st["cash"])
        self.init_cash = float(st.get("init_cash", init_cash))
        self.pos = {k: float(v) for k, v in st.get("positions", {}).items()}
        self.history = st.get("history", [])
        self.trades = st.get("trades", [])

    def value(self, prices: dict | None = None) -> float:
        prices = prices or {}
        mv = sum(q * prices[s] for s, q in self.pos.items() if s in prices)
        return float(self.cash + mv)

    def positions(self) -> dict:
        return dict(self.pos)

    def rebalance_to(self, target_weights: dict, prices: dict,
                     commission: float = 0.002, sell_cost: float = 0.0,
                     lot: int = 1, when: str | None = None) -> dict:
        orders = compute_orders(target_weights, prices, self.value(prices),
                                self.pos, lot=lot, allow_fractional=False)
        for s in sorted(orders, key=lambda x: orders[x]):   # 先卖后买 | sell first
            delta, price = orders[s], prices[s]
            trade_val = abs(delta) * price
            cost = trade_val * commission + (trade_val * sell_cost if delta < 0 else 0.0)
            self.cash -= delta * price + cost
            self.pos[s] = self.pos.get(s, 0.0) + delta
            if abs(self.pos[s]) < 1e-9:
                del self.pos[s]
            self.trades.append({"time": when, "symbol": s, "qty": delta,
                                "price": round(price, 4), "cost": round(cost, 2)})
        return orders

    def record(self, prices: dict, when: str | None = None) -> None:
        self.history.append({"time": when, "equity": round(self.value(prices), 2),
                             "cash": round(self.cash, 2)})

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"cash": self.cash, "init_cash": self.init_cash,
                       "positions": self.pos, "history": self.history,
                       "trades": self.trades}, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- Alpaca 真券商 | real
class AlpacaBroker(Broker):
    """
    Alpaca 美股适配器(默认纸面端点)。账户/持仓/下单走 Alpaca;现价由调用方传入。
    Alpaca US adapter (paper endpoint by default). Account/positions/orders via Alpaca.

    需要:pip install -e ".[broker]" + 环境变量 ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY。
    测试可注入 client(mock),绕开真实网络。| Inject a mock client for offline tests.
    """

    def __init__(self, paper: bool = True, client=None, key: str | None = None,
                 secret: str | None = None):
        self._real = False
        if client is not None:
            self._client = client                 # 注入(测试)| injected (tests)
            return
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as e:
            raise ImportError("未装 alpaca-py:pip install -e \".[broker]\"") from e
        key = key or os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("APCA_API_KEY_ID")
        secret = (secret or os.environ.get("ALPACA_API_SECRET_KEY")
                  or os.environ.get("APCA_API_SECRET_KEY"))
        if not (key and secret):
            raise RuntimeError("缺 Alpaca 密钥:设 ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY")
        self._client = TradingClient(key, secret, paper=paper)
        self._real = True

    @property
    def cash(self) -> float:
        return float(self._client.get_account().cash)

    def value(self, prices: dict | None = None) -> float:
        """总权益 = Alpaca 账户 equity(真实,不依赖传入价)。| Real account equity."""
        return float(self._client.get_account().equity)

    def positions(self) -> dict:
        return {p.symbol: float(p.qty) for p in self._client.get_all_positions()}

    def rebalance_to(self, target_weights: dict, prices: dict,
                     commission: float = 0.0, sell_cost: float = 0.0,
                     lot: int = 1, when: str | None = None) -> dict:
        """按目标权重向 Alpaca 提交市价单(美股允许小数股)。| Submit market orders to Alpaca."""
        orders = compute_orders(target_weights, prices, self.value(prices),
                                self.positions(), lot=1, allow_fractional=True)
        for s in sorted(orders, key=lambda x: orders[x]):   # 先卖后买 | sell first
            self._submit(s, abs(orders[s]), "buy" if orders[s] > 0 else "sell")
        return orders

    def _submit(self, symbol: str, qty: float, side: str) -> None:
        if self._real:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            self._client.submit_order(MarketOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY))
        else:                                     # 注入的 mock | injected mock
            self._client.submit_order({"symbol": symbol, "qty": qty, "side": side})
