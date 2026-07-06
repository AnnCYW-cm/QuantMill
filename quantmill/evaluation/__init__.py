"""
metrics.py —— 核心指标汇总与对比
metrics.py —— Core metric summary and comparison
================================
把回测结果提炼成"人能一眼看懂的几个关键数",并和买入持有对比。
Distill backtest results into "a few key numbers anyone can grasp at a glance",
and compare them against buy & hold.

衡量策略永远不只看收益(Day 1 核心认知),一起看:
Evaluating a strategy is never just about return (a Day 1 core insight); look at all of these together:
    - 收益 Return
    - 收益 Return
    - 夏普 Sharpe(每份风险换多少收益,>1 不错)
    - 夏普 Sharpe (how much return per unit of risk, >1 is decent)
    - 最大回撤 Max Drawdown(能不能扛住的关键)
    - 最大回撤 Max Drawdown (the key to whether you can withstand it)
    - vs 买入持有(跑不赢它=白忙活)
    - vs 买入持有 Buy & Hold (if you can't beat it, all the effort is wasted)

关键补充:backtesting.py 不给"买入持有的回撤",这里自己从价格算出来,
        因为策略真正的价值常常是【用更小的回撤,换取相近的收益】。
Key addition: backtesting.py does not provide "buy & hold drawdown", so we compute it
        ourselves from prices, because a strategy's real value often lies in
        [trading a smaller drawdown for a comparable return].
"""

from __future__ import annotations

import pandas as pd


def buy_hold_max_drawdown(close: pd.Series) -> float:
    """买入持有的最大回撤(%):一直拿着,从最高点跌到谷底最多亏多少。
    Max drawdown of buy & hold (%): if you just hold, the largest loss from peak to trough.
    """
    equity = close / close.iloc[0]
    dd = equity / equity.cummax() - 1.0
    return float(dd.min() * 100)


def summarize(stats, close: pd.Series) -> dict:
    """把 backtesting.py 的 stats 提炼成对比字典。close 用来算买入持有回撤。
    Distill backtesting.py's stats into a comparison dict. `close` is used to compute buy & hold drawdown.
    """
    strat_ret = float(stats["Return [%]"])
    bh_ret = float(stats["Buy & Hold Return [%]"])
    strat_dd = float(stats["Max. Drawdown [%]"])
    bh_dd = buy_hold_max_drawdown(close)

    return {
        "区间": f"{stats['Start'].date()} ~ {stats['End'].date()}",
        "策略收益%": round(strat_ret, 1),
        "买入持有收益%": round(bh_ret, 1),
        "跑赢买入持有": strat_ret > bh_ret,
        "策略最大回撤%": round(strat_dd, 1),
        "买入持有最大回撤%": round(bh_dd, 1),
        "回撤更小": strat_dd > bh_dd,     # 回撤是负数,更大(更接近0)=更小的亏 | Drawdown is negative; larger (closer to 0) = smaller loss
        "夏普": round(float(stats["Sharpe Ratio"]), 2),
        "Sortino": round(float(stats.get("Sortino Ratio", float("nan"))), 2),
        "Calmar": round(float(stats.get("Calmar Ratio", float("nan"))), 2),
        "交易次数": int(stats["# Trades"]),
        "胜率%": round(float(stats["Win Rate [%]"]), 1),
    }


def verdict(s: dict) -> str:
    """一句话结论:这个策略到底行不行。
    One-line verdict: whether this strategy actually works or not.
    """
    beat_ret = s["跑赢买入持有"]
    smaller_dd = s["回撤更小"]
    if beat_ret and smaller_dd:
        return "✅ 又多赚又更稳(收益更高+回撤更小)—— 这才是好策略,继续验证别的标的/时段"
    if smaller_dd and not beat_ret:
        return ("🟡 收益输给买入持有,但回撤更小(更稳)。模型价值在'避险'—— "
                "适合怕大回撤的人;想赢总收益还需更好的特征/标注")
    if beat_ret and not smaller_dd:
        return "🟡 收益跑赢了但回撤没变小,是靠多冒险换的,注意心理承受"
    return ("🔴 收益和回撤都没赢过买入持有 —— 在这个标的上还不如无脑拿着。"
            "正常!换震荡/熊市标的,或改进特征再试。诚实面对是量化第一课")


if __name__ == "__main__":
    from quantmill.backtest import run_ml_backtest
    from quantmill.data import get_ohlcv
    from quantmill.factor import build_dataset
    from quantmill.model import walk_forward

    df = get_ohlcv("AAPL", "us", start="2018-01-01", end="2024-01-01")
    X, y, feat_df = build_dataset(df, horizon=5)
    proba = walk_forward(X, y)
    bt, stats = run_ml_backtest(feat_df, proba)
    s = summarize(stats, feat_df.loc[proba.dropna().index, "Close"])
    for k, v in s.items():
        print(f"{k:.<16} {v}")
    print("\n结论:", verdict(s))
