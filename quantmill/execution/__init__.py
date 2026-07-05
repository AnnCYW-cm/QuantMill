"""
execution —— 执行层 | Execution layer
======================================
把信号真正"下单"出去(先纸面模拟)。数据→信号→目标权重→下单成交→持仓/盈亏,闭环。

  broker   券商抽象 + 本地纸面账户(PaperBroker)| broker abstraction + paper account
  engine   纸面交易闭环:run / status / reset | paper-trading loop

⚠️ 真券商(Alpaca/QMT)需账号+密钥,AlpacaBroker 留桩;当前 PaperBroker 本地模拟。
"""

from quantmill.execution.broker import AlpacaBroker, Broker, PaperBroker
from quantmill.execution.engine import paper_reset, paper_run, paper_status

__all__ = [
    "Broker", "PaperBroker", "AlpacaBroker",
    "paper_run", "paper_status", "paper_reset",
]
