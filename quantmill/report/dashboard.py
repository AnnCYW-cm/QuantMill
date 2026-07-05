"""
dashboard.py —— 自选股扫描 + 今日信号面板
dashboard.py —— Watchlist scanner + "today's signal" panel
==========================================================
把工具从"回顾历史"变成"每天能看一眼":对自选股池,给出【截止最新数据日】
每只票的信号——该持有还是空仓,以及模型的把握有多大。
Turns the tool from "reviewing history" into "check it daily": for a watchlist,
give each stock's signal as of the LATEST data date — hold or stay in cash, and
how confident the model is.

一页看清 / One page shows:
    今日信号(持有🟢/空仓🔴/观望🟡) · 模型置信度 P(涨) · 历史是否跑赢买入持有 · 夏普
    today's signal (hold/cash/wait) · confidence P(up) · did it beat buy&hold historically · Sharpe

诚实前提 / Honest caveat:
    信号基于本工具的简单价量模型,该模型在广度验证里【没有稳定超额收益】(见 validate.py)。
    Signals come from this tool's simple price-volume model, which has NO stable edge in
    breadth validation (see validate.py). 面板仅供研究,不是买卖建议。For research only, not advice.
"""

from __future__ import annotations

import os

import pandas as pd

from quantmill import config
from quantmill.backtest import run_ml_backtest
from quantmill.credibility.validate import QUICK_UNIVERSE, _quiet
from quantmill.data import get_ohlcv
from quantmill.evaluation import summarize
from quantmill.factor import FEATURE_COLS, build_dataset, make_features
from quantmill.model import train_full, walk_forward
from quantmill.watchlist import load_watchlist


def _signal(p_up: float, buy_th: float, sell_th: float) -> str:
    """把概率翻译成人话信号。| Translate probability into a plain-language signal."""
    if p_up > buy_th:
        return "持有 🟢"
    if p_up < sell_th:
        return "空仓 🔴"
    return "观望 🟡"


def scan_one(symbol, market, start, end, horizon, buy_th, sell_th,
             cash, commission):
    """
    扫描一只票:训练模型 -> 算截止最新一天的 P(涨) -> 今日信号;
    Scan one stock: train model -> compute P(up) as of the latest day -> today's signal;
    再跑一遍样本外回测,给出"这套信号历史上可不可信"。
    also run the out-of-sample backtest to say "is this signal historically trustworthy".
    """
    df = get_ohlcv(symbol, market, start=start, end=end)
    X, y, feat_df = build_dataset(df, horizon=horizon)

    # --- 今日信号:用全部历史训练,预测【最新一根有效特征】那天 ---
    # --- Today's signal: train on all history, predict the LATEST valid-feature day ---
    model = train_full(X, y)
    live = make_features(df)[FEATURE_COLS].dropna()  # 丢掉开头 rolling 不足的行 | drop early rows with insufficient rolling
    live_row = live.iloc[-1:]                          # 最新一天的特征 | latest day's features
    live_date = live.index[-1].date()
    p_up = float(model.predict_proba(live_row)[0, 1])

    # --- 历史成色:样本外回测,是否跑赢买入持有 ---
    # --- Track record: out-of-sample backtest, did it beat buy & hold ---
    proba = walk_forward(X, y, n_splits=5)
    with _quiet():
        _, stats = run_ml_backtest(feat_df, proba, cash=cash, commission=commission,
                                   buy_th=buy_th, sell_th=sell_th)
    close = feat_df.loc[proba.dropna().index, "Close"]
    s = summarize(stats, close)

    return {
        "标的": f"{market}:{symbol}",
        "数据截止": str(live_date),
        "今日信号": _signal(p_up, buy_th, sell_th),
        "P(涨)": round(p_up, 3),
        "近20天%": round(float(live_row["ret_20d"].iloc[0]) * 100, 1),
        "历史跑赢": "是" if s["跑赢买入持有"] else "否",
        "策略%": s["策略收益%"], "买入持有%": s["买入持有收益%"],
        "夏普": s["夏普"],
    }


def scan(watchlist=None, start=config.START, end=None, horizon=config.HORIZON,
         buy_th=config.BUY_TH, sell_th=config.SELL_TH, cash=config.CASH,
         commission=config.COMMISSION):
    """扫描整个自选股池,返回结果 DataFrame(按 P(涨) 从高到低排序)。
    Scan the whole watchlist; return a DataFrame sorted by P(up) descending."""
    watchlist = watchlist or load_watchlist()   # 默认读 watchlist.txt | default: read watchlist.txt
    rows = []
    print("=" * 64)
    print("自选股扫描:算每只票截止最新数据日的今日信号")
    print("=" * 64)
    for market, syms in watchlist.items():
        for sym in syms:
            key = f"{market}:{sym}"
            try:
                r = scan_one(sym, market, start, end, horizon, buy_th, sell_th,
                             cash, commission)
                rows.append(r)
                print(f"  ✓ {r['标的']:<12} {r['今日信号']}  "
                      f"P(涨)={r['P(涨)']}  截止 {r['数据截止']}")
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {key:<12} 跳过:{type(e).__name__} {e}")
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("P(涨)", ascending=False).reset_index(drop=True)
    return df


_RESULTS_DIR = config.RESULTS_DIR


def _signal_class(sig: str) -> str:
    """信号 -> CSS 颜色类。| Signal -> CSS color class."""
    if "持有" in sig:
        return "hold"
    if "空仓" in sig:
        return "cash"
    return "wait"


def generate_dashboard(df: pd.DataFrame, buy_th=config.BUY_TH,
                       sell_th=config.SELL_TH) -> str:
    """把扫描结果出成一页自选股信号面板。| Render the scan into a one-page signal panel."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, "dashboard.html")

    if df.empty:
        rows, scan_date, n_hold = "", "-", 0
    else:
        scan_date = df["数据截止"].max()
        n_hold = int(df["今日信号"].str.contains("持有").sum())
        rows = "".join(
            f"<tr><td>{r['标的']}</td>"
            f"<td class='{_signal_class(r['今日信号'])}'>{r['今日信号']}</td>"
            f"<td>{r['P(涨)']}</td><td>{r['近20天%']}</td>"
            f"<td>{r['历史跑赢']}</td>"
            f"<td>{r['策略%']}</td><td>{r['买入持有%']}</td><td>{r['夏普']}</td>"
            f"<td>{r['数据截止']}</td></tr>"
            for _, r in df.iterrows()
        )

    n = len(df)
    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>自选股信号面板 Watchlist Signals</title>
<style>
  body {{ font-family:-apple-system,"PingFang SC",sans-serif; max-width:900px;
         margin:40px auto; padding:0 20px; color:#222; line-height:1.6; }}
  h1 {{ font-size:22px; }}
  .sub {{ color:#666; font-size:14px; }}
  table {{ border-collapse:collapse; width:100%; margin:16px 0; font-size:14px; }}
  th,td {{ border:1px solid #ddd; padding:8px 10px; text-align:right; }}
  th:first-child,td:first-child {{ text-align:left; }}
  th {{ background:#f5f5f7; position:sticky; top:0; }}
  .hold {{ background:#e6f7ea; color:#137333; font-weight:600; }}
  .cash {{ background:#fdecea; color:#b3261e; font-weight:600; }}
  .wait {{ background:#fff8e1; color:#a06a00; font-weight:600; }}
  .warn {{ background:#fff8e1; border-left:4px solid #f4b400; padding:12px 16px;
          border-radius:4px; margin:16px 0; font-size:14px; }}
  .foot {{ color:#888; font-size:13px; margin-top:28px; border-top:1px solid #eee;
          padding-top:12px; }}
</style></head><body>
<h1>📊 自选股信号面板 · Watchlist Signals</h1>
<p class="sub">数据截止 {scan_date} · 共 {n} 只 · 其中 {n_hold} 只"持有"信号 ·
   阈值 持有&gt;{buy_th} / 空仓&lt;{sell_th} · 按看涨概率排序</p>

<div class="warn"><b>⚠️ 诚实提示:</b>信号来自本工具的简单价量模型,该模型在广度验证中
   <b>没有稳定的超额收益</b>(仅 2/15 跑赢买入持有,详见 validation_report.html)。
   此面板<b>仅供研究和学习</b>,不是买卖建议,别拿真钱跟。</div>

<table>
  <tr><th>标的</th><th>今日信号</th><th>P(涨)</th><th>近20天%</th>
      <th>历史跑赢</th><th>策略%</th><th>买入持有%</th><th>夏普</th><th>数据截止</th></tr>
  {rows}
</table>

<div class="foot">
  信号含义:🟢持有=模型看涨且有把握 · 🔴空仓=看跌应避险 · 🟡观望=没把握。<br>
  "历史跑赢"= 这只票上策略样本外回测是否赢过买入持有(否=这信号在它身上历史并不灵)。<br>
  刷新:<code>./.venv/bin/python -m quantmill.report.dashboard</code>
</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def run(watchlist=None, start=config.START, end=None, horizon=config.HORIZON,
        buy_th=config.BUY_TH, sell_th=config.SELL_TH):
    """扫描 + 出面板。| Scan + render panel."""
    df = scan(watchlist, start=start, end=end, horizon=horizon,
              buy_th=buy_th, sell_th=sell_th)
    if not df.empty:
        print("\n" + df.to_string(index=False))
    path = generate_dashboard(df, buy_th, sell_th)
    print(f"\n📄 信号面板已生成:{path}")
    return df


def main():
    import argparse
    p = argparse.ArgumentParser(description="自选股信号面板 | Watchlist signal panel")
    p.add_argument("--quick", action="store_true", help="小股票池快速试跑 | small watchlist")
    p.add_argument("--start", default=config.START)
    p.add_argument("--end", default=None)
    p.add_argument("--horizon", type=int, default=config.HORIZON)
    a = p.parse_args()
    run(QUICK_UNIVERSE if a.quick else None,   # None -> 读 watchlist.txt | None -> read watchlist.txt
        start=a.start, end=a.end, horizon=a.horizon)


if __name__ == "__main__":
    main()
