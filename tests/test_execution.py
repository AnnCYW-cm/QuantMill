# -*- coding: utf-8 -*-
"""
test_execution.py —— 本地纸面账户的成交/估值/持久化正确性
test_execution.py —— PaperBroker fills / valuation / persistence correctness
============================================================================
"""

import types

from quantmill.execution.broker import (
    PaperBroker, AlpacaBroker, compute_orders,
)


def _broker(tmp_path, cash=10_000.0):
    return PaperBroker(path=str(tmp_path / "acct.json"), init_cash=cash)


class _MockAlpaca:
    """假 Alpaca client:返回假账户/持仓,记录提交的订单。| Fake Alpaca client for offline tests."""
    def __init__(self, equity, cash, positions):
        self._acct = types.SimpleNamespace(equity=str(equity), cash=str(cash))
        self._pos = [types.SimpleNamespace(symbol=s, qty=str(q))
                     for s, q in positions.items()]
        self.submitted = []

    def get_account(self):
        return self._acct

    def get_all_positions(self):
        return self._pos

    def submit_order(self, order):
        self.submitted.append(order)


# ---------------------------------------------------------------- 纯逻辑 | compute_orders
def test_compute_orders_whole_vs_fractional():
    assert compute_orders({"A": 1.0}, {"A": 300.0}, 10_000, {})["A"] == 33.0   # 整股
    frac = compute_orders({"A": 1.0}, {"A": 300.0}, 10_000, {}, allow_fractional=True)
    assert abs(frac["A"] - 33.3333) < 0.01                                     # 小数股


def test_compute_orders_close_and_missing_price():
    assert compute_orders({}, {"A": 100.0}, 10_000, {"A": 50})["A"] == -50     # 清仓
    assert compute_orders({"A": 1.0}, {}, 10_000, {}) == {}                    # 缺价跳过


# ---------------------------------------------------------------- Alpaca 适配器(mock)
def test_alpaca_buys_via_mock_client():
    """AlpacaBroker 用注入的 mock:账户估值/持仓/提交订单正确。| Adapter logic via mock."""
    client = _MockAlpaca(equity=10_000, cash=10_000, positions={})
    b = AlpacaBroker(client=client)
    assert b.value() == 10_000.0 and b.positions() == {}
    b.rebalance_to({"AAPL": 0.5, "MSFT": 0.5}, {"AAPL": 100.0, "MSFT": 50.0})
    sides = {o["symbol"]: o["side"] for o in client.submitted}
    assert sides == {"AAPL": "buy", "MSFT": "buy"}


def test_alpaca_closes_position_via_mock():
    """目标里没有的持仓 -> 向 Alpaca 提交卖单。| Absent name -> sell order submitted."""
    client = _MockAlpaca(equity=10_000, cash=5_000, positions={"AAPL": 50})
    b = AlpacaBroker(client=client)
    b.rebalance_to({"MSFT": 1.0}, {"AAPL": 100.0, "MSFT": 50.0})
    byname = {o["symbol"]: o["side"] for o in client.submitted}
    assert byname["AAPL"] == "sell" and byname["MSFT"] == "buy"


def test_rebalance_buys_to_target(tmp_path):
    """等权买入到目标:持仓正确、现金相应扣减(零成本时精确)。| Buy to target weights."""
    b = _broker(tmp_path)
    prices = {"A": 100.0, "B": 50.0}
    b.rebalance_to({"A": 0.5, "B": 0.5}, prices, commission=0.0)
    assert b.positions() == {"A": 50.0, "B": 100.0}     # 5000/100=50, 5000/50=100
    assert abs(b.cash) < 1e-6                            # 全部买满 | fully invested
    assert abs(b.value(prices) - 10_000.0) < 1e-6       # 权益守恒 | equity preserved


def test_whole_lots_leaves_cash(tmp_path):
    """整股成交:买不满的部分留现金。| Whole-share fills leave leftover cash."""
    b = _broker(tmp_path)
    b.rebalance_to({"A": 1.0}, {"A": 300.0}, commission=0.0)
    assert b.positions()["A"] == 33.0                   # floor(10000/300)=33
    assert abs(b.cash - (10_000 - 33 * 300)) < 1e-6     # 剩 100


def test_commission_reduces_cash(tmp_path):
    """手续费从现金里扣。| Commission is deducted from cash."""
    b0 = _broker(tmp_path, cash=10_000)
    b0.rebalance_to({"A": 1.0}, {"A": 100.0}, commission=0.0)
    cash_nocost = b0.cash
    b1 = PaperBroker(path=str(tmp_path / "acct2.json"), init_cash=10_000)
    b1.rebalance_to({"A": 1.0}, {"A": 100.0}, commission=0.01)
    assert b1.cash < cash_nocost                        # 有手续费现金更少


def test_close_position(tmp_path):
    """目标里没有的持仓会被清仓,卖出加现金。| Names absent from target get closed."""
    b = _broker(tmp_path)
    b.rebalance_to({"A": 1.0}, {"A": 100.0}, commission=0.0)   # 建仓 A
    assert "A" in b.positions()
    b.rebalance_to({"B": 1.0}, {"A": 100.0, "B": 50.0}, commission=0.0)  # 目标改成 B
    assert "A" not in b.positions()                     # A 已清仓
    assert "B" in b.positions()


def test_persistence_roundtrip(tmp_path):
    """存盘后重载,状态一致。| Save then reload -> same state."""
    p = str(tmp_path / "acct.json")
    b = PaperBroker(path=p, init_cash=10_000)
    b.rebalance_to({"A": 0.5}, {"A": 100.0}, commission=0.001, when="2020-01-01")
    b.record({"A": 100.0}, when="2020-01-01")
    b.save()
    b2 = PaperBroker(path=p)
    assert b2.cash == b.cash and b2.positions() == b.positions()
    assert len(b2.trades) == len(b.trades) == 1
    assert len(b2.history) == 1


def test_value_cash_only(tmp_path):
    """空仓时权益=现金。| Equity == cash when flat."""
    b = _broker(tmp_path, cash=12_345.0)
    assert b.value({"A": 100.0}) == 12_345.0
