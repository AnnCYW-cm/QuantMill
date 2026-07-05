"""
quantmill —— 一个从零搭起来的端到端量化研究工具箱
quantmill —— an end-to-end quant research toolkit built from scratch
==================================================================
全流程 / Full pipeline:
    数据抓取 → 特征工程 → 机器学习预测 → 信号接回回测 → 指标与报告
    data → features → ML prediction → backtest → metrics & report

模块 / Modules:
    data      统一多市场数据层(港股/美股/A股)
              unified multi-market data layer (HK / US / A-share)
    features  特征工程 + 打标注 / feature engineering + labeling
    model     LightGBM 涨跌预测 + 时序交叉验证
              LightGBM up/down prediction + time-series cross-validation
    backtest  把模型信号接回 backtesting.py
              feed model signals back into backtesting.py
    metrics   核心指标汇总 / core metrics summary
    report    生成 HTML 研究报告 / generate an HTML research report
"""

__all__ = ["data", "features", "model", "backtest", "metrics", "report"]
