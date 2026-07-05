# -*- coding: utf-8 -*-
"""
report.py —— 生成 HTML 研究报告
report.py —— Generate an HTML research report
================================
把一次完整回测的结论输出成一张自包含的 HTML:关键指标对比 + 结论 + 特征重要性。
Output the conclusions of a full backtest into a self-contained HTML page:
key-metric comparison + verdict + feature importance.
另外调用 backtesting.py 自带的 bt.plot() 存一张可交互的资金曲线图。
Additionally call backtesting.py's built-in bt.plot() to save an interactive equity-curve chart.
"""

from __future__ import annotations

import os

import pandas as pd

from quantmill import config
from quantmill.evaluation import verdict

_RESULTS_DIR = config.RESULTS_DIR


def _row(label, strat, bh, better: bool | None):
    """一行对比表格。better=True 时策略那格标绿。
    One row of the comparison table. When better=True, the strategy cell is highlighted green.
    """
    mark = ""
    if better is True:
        mark = ' class="win"'
    elif better is False:
        mark = ' class="lose"'
    return (f"<tr><td>{label}</td><td{mark}>{strat}</td>"
            f"<td>{bh}</td></tr>")


def generate(symbol, market, s: dict, importance: pd.Series,
             bt=None, horizon=5) -> str:
    """生成报告 HTML 文件,返回文件路径。s = metrics.summarize 的结果。
    Generate the report HTML file and return its path. s = the result of metrics.summarize.
    """
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    safe = symbol.replace("/", "_").replace(".", "_")
    path = os.path.join(_RESULTS_DIR, f"report_{market}_{safe}.html")

    # 资金曲线交互图(backtesting.py 自带),单独存一份 | Interactive equity-curve chart (built into backtesting.py), saved as a separate file
    chart_name = f"equity_{market}_{safe}.html"
    if bt is not None:
        try:
            bt.plot(filename=os.path.join(_RESULTS_DIR, chart_name),
                    open_browser=False)
        except Exception as e:
            print(f"[提示] 资金曲线图生成失败(不影响报告):{e}")
            chart_name = None

    imp_rows = "".join(
        f"<tr><td>{k}</td><td>{int(v)}</td></tr>"
        for k, v in importance.head(8).items()
    )

    rows = (
        _row("收益 %", s["策略收益%"], s["买入持有收益%"], s["跑赢买入持有"])
        + _row("最大回撤 %", s["策略最大回撤%"], s["买入持有最大回撤%"], s["回撤更小"])
        + f"<tr><td>夏普比率</td><td>{s['夏普']}</td><td>—</td></tr>"
        + f"<tr><td>交易次数</td><td>{s['交易次数']}</td><td>1(一直拿)</td></tr>"
        + f"<tr><td>胜率 %</td><td>{s['胜率%']}</td><td>—</td></tr>"
    )

    chart_link = (f'<p><a href="{chart_name}" target="_blank">'
                  f'📈 打开可交互资金曲线图</a></p>' if chart_name else "")

    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>量化研究报告 · {market.upper()}:{symbol}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; max-width: 760px;
         margin: 40px auto; padding: 0 20px; color: #222; line-height: 1.6; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 28px; color:#333; }}
  .meta {{ color:#666; font-size:14px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size:15px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ background:#f5f5f7; }}
  .win  {{ background:#e6f7ea; color:#137333; font-weight:600; }}
  .lose {{ background:#fdecea; color:#b3261e; }}
  .verdict {{ background:#fff8e1; border-left:4px solid #f4b400; padding:12px 16px;
             border-radius:4px; margin:16px 0; }}
  .foot {{ color:#888; font-size:13px; margin-top:32px; border-top:1px solid #eee;
          padding-top:12px; }}
</style></head><body>
<h1>量化研究报告 · {market.upper()}:{symbol}</h1>
<p class="meta">回测区间 {s['区间']} · 预测未来 {horizon} 天涨跌 · 含手续费+滑点 ·
   信号为样本外(walk-forward,无未来函数)</p>

<h2>策略 vs 买入持有</h2>
<table>
  <tr><th>指标</th><th>ML 策略</th><th>买入持有</th></tr>
  {rows}
</table>

<div class="verdict"><b>结论:</b>{verdict(s)}</div>
{chart_link}

<h2>模型最看重的特征</h2>
<table><tr><th>特征</th><th>重要性</th></tr>{imp_rows}</table>

<div class="foot">
  铁律提醒:历史回测≠未来收益。此报告用历史数据验证逻辑,不构成投资建议。<br>
  下一步:换不同标的/时段跑,看结论是否稳健;别用单一漂亮结果骗自己(过拟合是头号杀手)。
</div>
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    from quantmill.data import get_ohlcv
    from quantmill.factor import build_dataset
    from quantmill.model import walk_forward, train_full, feature_importance
    from quantmill.backtest import run_ml_backtest
    from quantmill.evaluation import summarize

    df = get_ohlcv("AAPL", "us", start="2018-01-01", end="2024-01-01")
    X, y, feat_df = build_dataset(df, horizon=5)
    proba = walk_forward(X, y)
    bt, stats = run_ml_backtest(feat_df, proba)
    s = summarize(stats, feat_df.loc[proba.dropna().index, "Close"])
    imp = feature_importance(train_full(X, y))
    path = generate("AAPL", "us", s, imp, bt=bt)
    print("报告已生成:", path)
