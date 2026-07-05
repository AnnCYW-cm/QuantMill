"""
validate.py —— 策略可信度验证层
validate.py —— Strategy credibility / robustness layer
========================================================
回答那个最要命的问题:这套策略到底是"真有优势",还是"单只股票的运气 + 参数过拟合"?
Answers the killer question: does this strategy have a real edge, or is it just
one lucky stock plus overfitted parameters?

两把尺子 / Two rulers:
  1. 广度检验 breadth  —— 跨市场批量跑一篮子股票,看在【多大比例】的股票上跑赢/更稳。
                          Run a whole basket across markets; see on what FRACTION it wins / is safer.
                          只在1只上赢=运气;大多数上都有优势=信号。
                          Winning on 1 stock = luck; an edge on most = signal.
  2. 稳健性 robustness —— 模型预测 proba 与阈值无关,所以算一次预测、复用它扫多套买卖阈值,
                          Model proba is independent of the threshold, so predict once and
                          reuse it to sweep many buy/sell thresholds.
                          看表现是平稳还是"一拨参数就崩"(崩=过拟合,实盘必死)。
                          See if performance is stable or "collapses when nudged" (= overfit, dead live).
"""

from __future__ import annotations

import contextlib
import os

import numpy as np
import pandas as pd

from quantmill import config
from quantmill.backtest import run_ml_backtest
from quantmill.credibility.stats import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe,
)
from quantmill.data import get_ohlcv
from quantmill.evaluation import summarize
from quantmill.factor import build_dataset
from quantmill.model import walk_forward

# 默认股票池:三市场各挑有代表性的(成长/防御/银行混搭,避免只挑牛股自欺)
# Default universe: representative names per market (growth/defensive/banks mixed,
# so we don't cherry-pick only bull stocks and fool ourselves).
DEFAULT_UNIVERSE = {
    "us": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "KO", "JNJ"],
    "hk": ["00700", "09988", "00939", "00005"],
    "cn": ["000001", "600519", "600036"],
}

# 快速版:每市场少几只,用于调试/试跑 | Quick version: fewer names per market, for debugging
QUICK_UNIVERSE = {
    "us": ["AAPL", "MSFT", "KO"],
    "hk": ["00700"],
    "cn": ["600519"],
}


def compute_proba(symbol, market, start, end, horizon):
    """算一只股票的样本外预测 proba(最贵的一步),连同特征表一起返回,供后续复用。
    Compute one stock's out-of-sample proba (the expensive step); return it with the
    feature table so downstream threshold sweeps can reuse it."""
    df = get_ohlcv(symbol, market, start=start, end=end)
    X, y, feat_df = build_dataset(df, horizon=horizon)
    proba = walk_forward(X, y, n_splits=5)
    return feat_df, proba


@contextlib.contextmanager
def _quiet():
    """临时屏蔽 stderr,挡掉 backtesting.py 的进度条刷屏。| Silence stderr to hide backtesting's progress bar."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
        yield


def _one_backtest(feat_df, proba, buy_th, sell_th, cash, commission):
    """用给定阈值回测一次,返回精简指标字典。| Backtest once at given thresholds; return a slim metrics dict."""
    with _quiet():
        bt, stats = run_ml_backtest(feat_df, proba, cash=cash, commission=commission,
                                    buy_th=buy_th, sell_th=sell_th)
    close = feat_df.loc[proba.dropna().index, "Close"]
    return summarize(stats, close)


# ----------------------------------------------------------------------
# 1. 广度检验 | Breadth test
# ----------------------------------------------------------------------
def breadth(universe=None, start=config.START, end=None, horizon=config.HORIZON,
            buy_th=config.BUY_TH, sell_th=config.SELL_TH, cash=config.CASH,
            commission=config.COMMISSION):
    """
    跨市场批量跑,聚合"多少比例跑赢/回撤更小/平均优势"。
    Run the basket across markets; aggregate "% beat / % smaller drawdown / avg edge".
    返回:(每只结果的 DataFrame, 已算好的 {symbol: (feat_df, proba)} 缓存供稳健性复用)
    Returns: (per-stock DataFrame, a {symbol:(feat_df,proba)} cache to reuse for robustness)
    """
    universe = universe or DEFAULT_UNIVERSE
    rows, cache = [], {}
    print("=" * 64)
    print("广度检验:批量跑一篮子股票(这一步最慢,在训练几十个模型)")
    print("=" * 64)
    for market, syms in universe.items():
        for sym in syms:
            key = f"{market}:{sym}"
            try:
                feat_df, proba = compute_proba(sym, market, start, end, horizon)
                cache[key] = (feat_df, proba)
                s = _one_backtest(feat_df, proba, buy_th, sell_th, cash, commission)
                rows.append({
                    "标的": key,
                    "策略%": s["策略收益%"], "买入持有%": s["买入持有收益%"],
                    "跑赢": s["跑赢买入持有"],
                    "策略回撤%": s["策略最大回撤%"], "持有回撤%": s["买入持有最大回撤%"],
                    "回撤更小": s["回撤更小"], "夏普": s["夏普"],
                })
                print(f"  ✓ {key:<12} 策略 {s['策略收益%']:>7}% vs 持有 "
                      f"{s['买入持有收益%']:>7}%  回撤 {s['策略最大回撤%']:>6}/"
                      f"{s['买入持有最大回撤%']:>6}")
            except Exception as e:  # noqa: BLE001  某只挂了不影响整体 | one failure won't stop the batch
                print(f"  ✗ {key:<12} 跳过:{type(e).__name__} {e}")

    df = pd.DataFrame(rows)
    _print_breadth_summary(df)
    return df, cache


def _print_breadth_summary(df: pd.DataFrame):
    """把一篮子结果聚合成"到底有没有优势"的结论。| Aggregate the basket into an edge verdict."""
    if df.empty:
        print("没有成功的样本,无法聚合。")
        return
    n = len(df)
    beat = int(df["跑赢"].sum())
    smaller = int(df["回撤更小"].sum())
    edge = (df["策略%"] - df["买入持有%"]).mean()   # 平均超额收益 | mean excess return
    print("\n" + "-" * 64)
    print(f"聚合结果(共 {n} 只):")
    print(f"  跑赢买入持有:  {beat}/{n}  ({beat / n:.0%})")
    print(f"  回撤更小:      {smaller}/{n}  ({smaller / n:.0%})")
    print(f"  平均超额收益:  {edge:+.1f}%   平均夏普:{df['夏普'].mean():.2f}")
    print("-" * 64)
    # 判读:收益类看是否明显过半,回撤类看是否大多数更稳
    # Read-out: for returns check if clearly above half; for drawdown check if mostly safer
    ret_edge = "有超额收益优势 ✅" if beat / n > 0.55 else \
               ("跟买入持有五五开,收益上没优势 ⚠️" if beat / n >= 0.45 else "收益上明显更差 🔴")
    dd_edge = "多数标的回撤更小,避险优势明显 ✅" if smaller / n > 0.6 else \
              "回撤没有稳定优势 ⚠️"
    print(f"  收益结论:{ret_edge}")
    print(f"  避险结论:{dd_edge}")
    print("  提醒:一两只跑赢是运气,要看整篮子的比例才算数。")


# ----------------------------------------------------------------------
# 2. 稳健性检验 | Robustness test
# ----------------------------------------------------------------------
def robustness(cache: dict, buy_ths=config.ROBUSTNESS_BUY_THS,
               cash=config.CASH, commission=config.COMMISSION):
    """
    复用广度阶段算好的 proba,扫描不同买入阈值(卖出阈值对称设为 1-buy_th),
    Reuse the proba computed in the breadth stage; sweep buy thresholds (sell = 1-buy_th),
    看整篮子的平均表现随阈值怎么变。平稳=稳健;剧烈波动/某点独好=过拟合。
    see how the basket's average performance changes with the threshold. Flat = robust;
    wild swings / one lucky point = overfit.
    """
    print("\n" + "=" * 64)
    print("稳健性检验:同一份预测,拨动买卖阈值,看结果稳不稳")
    print("=" * 64)
    print(f"{'买入阈值':>8} {'卖出阈值':>8} {'平均超额%':>10} {'跑赢比例':>9} "
          f"{'平均回撤%':>10}")
    print("-" * 52)
    summary = []
    for bt_th in buy_ths:
        sell_th = round(1 - bt_th, 3)
        edges, beats, dds = [], [], []
        for feat_df, proba in cache.values():
            try:
                s = _one_backtest(feat_df, proba, bt_th, sell_th, cash, commission)
                edges.append(s["策略收益%"] - s["买入持有收益%"])
                beats.append(1 if s["跑赢买入持有"] else 0)
                dds.append(s["策略最大回撤%"])
            except Exception:  # noqa: BLE001
                continue
        if not edges:
            continue
        avg_edge = sum(edges) / len(edges)
        beat_ratio = sum(beats) / len(beats)
        avg_dd = sum(dds) / len(dds)
        summary.append({"buy_th": bt_th, "sell_th": sell_th,
                        "avg_edge": avg_edge, "beat_ratio": beat_ratio,
                        "avg_dd": avg_dd})
        print(f"{bt_th:>8} {sell_th:>8} {avg_edge:>+10.1f} "
              f"{beat_ratio:>8.0%} {avg_dd:>10.1f}")
    print("-" * 52)
    if summary:
        edges = [x["avg_edge"] for x in summary]
        spread = max(edges) - min(edges)
        print(f"  平均超额收益跨阈值波动幅度:{spread:.1f} 个百分点")
        print("  → 波动小 = 稳健(不挑参数);波动大/只有某个阈值好 = 过拟合警告 ⚠️")
    return pd.DataFrame(summary)


# ----------------------------------------------------------------------
# 3. 统计严谨体检:DSR + PBO(平台护城河)| Statistical rigor: DSR + PBO
# ----------------------------------------------------------------------
def _grid_return_matrix(feat_df, proba, buy_ths, cash, commission):
    """把阈值网格里每组配置的【每日收益】拼成 (日期 × 配置) 矩阵。
    Build a (dates × configs) daily-return matrix from the threshold grid."""
    cols = {}
    for bt_th in buy_ths:
        sell_th = round(1 - bt_th, 3)
        with _quiet():
            _, stats = run_ml_backtest(feat_df, proba, cash=cash,
                                       commission=commission,
                                       buy_th=bt_th, sell_th=sell_th)
        equity = stats["_equity_curve"]["Equity"]
        cols[bt_th] = equity.pct_change()
    return pd.DataFrame(cols).dropna()


def symbol_credibility(feat_df, proba, buy_ths, cash, commission):
    """一只股票的统计体检:在阈值网格上算 DSR(最优配置去膨胀夏普)+ PBO(过拟合概率)。
    Per-stock statistical check: DSR of the best config + PBO over the threshold grid.
    """
    mat = _grid_return_matrix(feat_df, proba, buy_ths, cash, commission)
    if mat.shape[0] < 30 or mat.shape[1] < 2:
        return None
    sr_trials = [sharpe(mat[c].to_numpy()) for c in mat.columns]  # 每组配置的单期夏普
    best_i = int(np.nanargmax(sr_trials))
    dsr = deflated_sharpe_ratio(mat.iloc[:, best_i].to_numpy(),
                                sr_trials=sr_trials)["dsr"]
    n_splits = min(10, (mat.shape[0] // 20) * 2 or 2)  # 段数不超过样本承受 | cap splits
    pbo = probability_of_backtest_overfitting(mat.to_numpy(), n_splits=n_splits)["pbo"]
    return {"best_th": float(mat.columns[best_i]), "dsr": float(dsr),
            "pbo": float(pbo), "n_configs": mat.shape[1]}


def credibility_pass(cache, buy_ths=config.ROBUSTNESS_BUY_THS,
                     cash=config.CASH, commission=config.COMMISSION):
    """对每只股票做 DSR/PBO 体检并聚合。cache 来自 breadth 阶段(已算好 proba)。
    Run DSR/PBO per stock and aggregate. cache comes from the breadth stage."""
    print("\n" + "=" * 64)
    print("统计严谨体检:DSR 去膨胀夏普 + PBO 回测过拟合概率")
    print("=" * 64)
    print(f"{'标的':<12} {'最优阈值':>8} {'DSR(真夏普>0概率)':>16} {'PBO(过拟合概率)':>14}")
    print("-" * 56)
    rows = []
    for key, (feat_df, proba) in cache.items():
        try:
            h = symbol_credibility(feat_df, proba, buy_ths, cash, commission)
        except Exception as e:  # noqa: BLE001
            h = None
            print(f"{key:<12} 跳过:{type(e).__name__}")
        if not h:
            continue
        rows.append({"标的": key, **h})
        dsr_mark = "✅" if h["dsr"] > 0.95 else ("🟡" if h["dsr"] > 0.5 else "🔴")
        pbo_mark = "✅" if h["pbo"] < 0.2 else ("🟡" if h["pbo"] < 0.5 else "🔴")
        print(f"{key:<12} {h['best_th']:>8} {h['dsr']:>13.1%} {dsr_mark} "
              f"{h['pbo']:>11.1%} {pbo_mark}")

    df = pd.DataFrame(rows)
    if not df.empty:
        n = len(df)
        sig = int((df["dsr"] > 0.95).sum())
        mean_pbo = df["pbo"].mean()
        print("-" * 56)
        print(f"聚合({n} 只):DSR 显著(>95%)的 {sig}/{n};平均 PBO {mean_pbo:.1%}")
        pbo_read = ("整体过拟合严重 🔴" if mean_pbo >= 0.5 else
                    ("有一定过拟合风险 🟡" if mean_pbo >= 0.3 else "过拟合可控 ✅"))
        print(f"  判读:调阈值这套流程 —— {pbo_read}")
        print("  DSR 低=优势可能是多重检验挑出来的运气;PBO 高=样本内最优在样本外站不住。")
    return df


# ----------------------------------------------------------------------
# 4. 汇总 HTML 报告 | Aggregate HTML report
# ----------------------------------------------------------------------
_RESULTS_DIR = config.RESULTS_DIR


def generate_report(breadth_df: pd.DataFrame, robust_df: pd.DataFrame,
                    cred_df: pd.DataFrame | None = None) -> str:
    """把广度 + 稳健性 + 统计体检汇成一张可信度报告。| Breadth + robustness + DSR/PBO report."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, "validation_report.html")

    n = len(breadth_df)
    beat = int(breadth_df["跑赢"].sum())
    smaller = int(breadth_df["回撤更小"].sum())
    edge = (breadth_df["策略%"] - breadth_df["买入持有%"]).mean()

    # 每只一行 | one row per stock
    b_rows = "".join(
        f"<tr><td>{r['标的']}</td>"
        f"<td class='{'win' if r['跑赢'] else 'lose'}'>{r['策略%']}</td>"
        f"<td>{r['买入持有%']}</td>"
        f"<td class='{'win' if r['回撤更小'] else ''}'>{r['策略回撤%']}</td>"
        f"<td>{r['持有回撤%']}</td><td>{r['夏普']}</td></tr>"
        for _, r in breadth_df.iterrows()
    )
    # 稳健性每档一行 | one row per threshold
    r_rows = "".join(
        f"<tr><td>{r['buy_th']}</td><td>{r['sell_th']}</td>"
        f"<td class='{'lose' if r['avg_edge'] < 0 else 'win'}'>{r['avg_edge']:+.1f}</td>"
        f"<td>{r['beat_ratio']:.0%}</td><td>{r['avg_dd']:.1f}</td></tr>"
        for _, r in robust_df.iterrows()
    ) if not robust_df.empty else ""

    spread = (robust_df["avg_edge"].max() - robust_df["avg_edge"].min()) \
        if not robust_df.empty else 0

    # ③ 统计体检 DSR/PBO | statistical checks
    has_cred = cred_df is not None and not cred_df.empty
    if has_cred:
        c_n = len(cred_df)
        c_sig = int((cred_df["dsr"] > 0.95).sum())
        c_mean_pbo = cred_df["pbo"].mean()
        c_rows = "".join(
            f"<tr><td>{r['标的']}</td><td>{r['best_th']}</td>"
            f"<td class='{'win' if r['dsr'] > 0.95 else ('lose' if r['dsr'] < 0.5 else '')}'>"
            f"{r['dsr']:.1%}</td>"
            f"<td class='{'win' if r['pbo'] < 0.2 else ('lose' if r['pbo'] >= 0.5 else '')}'>"
            f"{r['pbo']:.1%}</td></tr>"
            for _, r in cred_df.iterrows()
        )
        cred_section = f"""
<h2>③ 统计严谨体检 DSR + PBO —— 是真优势还是运气+过拟合?</h2>
<p style="font-size:14px">DSR 显著(&gt;95%)的 <b>{c_sig}/{c_n}</b> ·
   平均 PBO <b>{c_mean_pbo:.1%}</b>。
   <b>DSR</b>=扣除"试了 N 组参数"的选择偏差后、真夏普&gt;0 的概率(&gt;95% 才算显著);
   <b>PBO</b>=样本内最优配置在样本外跌破中位的概率(越低越好,≈50% 即挑参数纯靠运气)。</p>
<table><tr><th>标的</th><th>最优阈值</th><th>DSR</th><th>PBO</th></tr>{c_rows}</table>"""
    else:
        cred_section = ""

    # 结论 | verdict
    ret_ok = beat / n > 0.55 if n else False
    dd_ok = smaller / n > 0.6 if n else False
    if ret_ok and dd_ok:
        verdict = "✅ 整篮子上既多赚又更稳——有可信的优势,值得推进下一步(模拟盘)。"
    elif dd_ok and not ret_ok:
        verdict = ("🟡 收益上没能跑赢买入持有,但多数标的回撤更小——优势只在'避险'。"
                   "作为纯多头赚钱策略还不成立,但作为风控叠加层有价值。")
    else:
        verdict = ("🔴 整篮子看,收益和风险都没有稳定优势——之前个别标的的漂亮结果基本是"
                   "运气/挑样本。这套简单价量特征+模型还没有真实 alpha。诚实面对,这正是"
                   "验证层存在的意义:它拦住了一个'看着能赚其实不能'的策略。")

    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>策略可信度报告 Strategy Credibility Report</title>
<style>
  body {{ font-family:-apple-system,"PingFang SC",sans-serif; max-width:820px;
         margin:40px auto; padding:0 20px; color:#222; line-height:1.6; }}
  h1 {{ font-size:22px; }} h2 {{ font-size:17px; margin-top:28px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }}
  th,td {{ border:1px solid #ddd; padding:7px 10px; text-align:right; }}
  th:first-child,td:first-child {{ text-align:left; }}
  th {{ background:#f5f5f7; }}
  .win {{ background:#e6f7ea; color:#137333; font-weight:600; }}
  .lose {{ background:#fdecea; color:#b3261e; }}
  .box {{ background:#fff8e1; border-left:4px solid #f4b400; padding:12px 16px;
         border-radius:4px; margin:16px 0; }}
  .foot {{ color:#888; font-size:13px; margin-top:32px; border-top:1px solid #eee;
          padding-top:12px; }}
</style></head><body>
<h1>策略可信度报告 · Strategy Credibility Report</h1>
<p style="color:#666;font-size:14px">
  跨市场批量验证 · 目的:分清"真优势"还是"运气+过拟合" /
  Multi-market batch validation: real edge vs luck + overfit</p>

<div class="box"><b>总结论 Verdict:</b><br>{verdict}</div>

<h2>① 广度检验 Breadth —— 在多少比例的股票上有优势?</h2>
<p style="font-size:14px">共 {n} 只:跑赢买入持有 <b>{beat}/{n} ({beat/n:.0%})</b> ·
   回撤更小 <b>{smaller}/{n} ({smaller/n:.0%})</b> ·
   平均超额收益 <b>{edge:+.1f}%</b></p>
<table><tr><th>标的</th><th>策略%</th><th>买入持有%</th><th>策略回撤%</th>
  <th>持有回撤%</th><th>夏普</th></tr>{b_rows}</table>

<h2>② 稳健性检验 Robustness —— 拨动阈值,结果稳不稳?</h2>
<p style="font-size:14px">平均超额收益随阈值波动 <b>{spread:.1f}</b> 个百分点。
   波动小=稳健;某个阈值独好=过拟合警告。</p>
<table><tr><th>买入阈值</th><th>卖出阈值</th><th>平均超额%</th><th>跑赢比例</th>
  <th>平均回撤%</th></tr>{r_rows}</table>
{cred_section}

<div class="foot">
  铁律:代码能跑 ≠ 策略能赚;单只漂亮 ≠ 整体有效。<br>
  本报告用历史数据批量验证逻辑,不构成投资建议。真优势需在多标的+多时段稳定复现。
</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def run_all(universe=None, start=config.START, end=None, horizon=config.HORIZON,
            buy_th=config.BUY_TH, sell_th=config.SELL_TH, cash=config.CASH,
            commission=config.COMMISSION, buy_ths=config.ROBUSTNESS_BUY_THS):
    """完整验证:广度 + 稳健性 + 出报告。| Full validation: breadth + robustness + report."""
    b_df, cache = breadth(universe, start, end, horizon, buy_th, sell_th,
                          cash, commission)
    r_df = robustness(cache, buy_ths, cash, commission)
    c_df = credibility_pass(cache, buy_ths, cash, commission)
    path = generate_report(b_df, r_df, c_df)
    print(f"\n📄 可信度报告已生成:{path}")
    return b_df, r_df, c_df


def main():
    import argparse
    p = argparse.ArgumentParser(description="策略可信度验证 | Strategy credibility validation")
    p.add_argument("--quick", action="store_true",
                   help="用小股票池快速试跑 | small universe, fast")
    p.add_argument("--start", default=config.START)
    p.add_argument("--end", default=None)
    p.add_argument("--horizon", type=int, default=config.HORIZON)
    a = p.parse_args()
    if a.quick:
        universe = QUICK_UNIVERSE
    else:
        from quantmill.watchlist import load_watchlist  # 惰性导入防循环 | lazy import avoids cycle
        universe = load_watchlist()
    run_all(universe, start=a.start, end=a.end, horizon=a.horizon)


if __name__ == "__main__":
    main()
