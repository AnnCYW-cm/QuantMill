"""
pipeline.py —— 单只标的的完整流程(数据→特征→模型→回测→报告)
pipeline.py —— Full single-stock pipeline (data→features→model→backtest→report)
================================================================================
把"深挖一只票"的业务逻辑收进包里,供 CLI(quantmill analyze)复用。
Keeps the "deep-dive one stock" logic inside the package, reused by the CLI.
"""

from __future__ import annotations

from quantmill import config
from quantmill.backtest import run_ml_backtest
from quantmill.data import get_ohlcv
from quantmill.evaluation import summarize, verdict
from quantmill.factor import build_dataset
from quantmill.model import feature_importance, time_series_cv, train_full, walk_forward
from quantmill.report import generate


def run_single(symbol, market, start=config.START, end=None,
               horizon=config.HORIZON, buy_th=config.BUY_TH,
               sell_th=config.SELL_TH, cash=config.CASH, do_cv=True):
    """深挖一只票:跑完整流程并生成 HTML 报告,返回指标字典。
    Deep-dive one stock: run the full pipeline, generate the HTML report, return metrics."""
    print("=" * 60)
    print(f"量化流水线启动:{market.upper()}:{symbol}")
    print("=" * 60)

    # 1. 数据 | Data
    df = get_ohlcv(symbol, market, start=start, end=end)

    # 2. 特征 + 标注 | Features + labeling
    X, y, feat_df = build_dataset(df, horizon=horizon)
    print(f"[特征] {X.shape[0]} 行 × {X.shape[1]} 特征 · "
          f"标注涨占比 {y.mean():.1%}")

    # 3. 模型评估(时序交叉验证) | Model evaluation (time-series cross-validation)
    if do_cv:
        time_series_cv(X, y, n_splits=config.N_SPLITS)

    # 4. 样本外预测 -> 回测 | Out-of-sample prediction -> backtest
    proba = walk_forward(X, y, n_splits=config.N_SPLITS)
    bt, stats = run_ml_backtest(feat_df, proba, cash=cash,
                                buy_th=buy_th, sell_th=sell_th)

    # 5. 指标汇总 | Metrics summary
    close = feat_df.loc[proba.dropna().index, "Close"]
    s = summarize(stats, close)
    print("\n" + "-" * 40)
    print("回测结果(策略 vs 买入持有):")
    print("-" * 40)
    for k, v in s.items():
        print(f"{k:.<18} {v}")
    print("\n结论:", verdict(s))

    # 6. 报告 | Report
    imp = feature_importance(train_full(X, y))
    path = generate(symbol, market, s, imp, bt=bt, horizon=horizon)
    print(f"\n📄 报告已生成:{path}")
    print("   用浏览器打开即可查看完整对比与资金曲线。")
    return s
