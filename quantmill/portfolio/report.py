"""
report.py —— 组合回测 HTML 报告(策略 vs 等权基准)| Portfolio backtest report
==============================================================================
核心问题:我们信号选出来的组合,到底能不能赢过"无脑等权持有整个池"?
Core question: does our signal-picked portfolio beat naive equal-weight?
"""

from __future__ import annotations

import os

import pandas as pd

from quantmill import config

_RESULTS_DIR = config.RESULTS_DIR


def _equity_svg(strat_eq: pd.Series, bench_eq: pd.Series,
                w: int = 740, h: int = 220, pad: int = 28) -> str:
    """两条资金曲线的内联 SVG(策略绿、基准灰)。| Inline SVG of two equity curves."""
    s, b = strat_eq.to_numpy(), bench_eq.to_numpy()
    n = len(s)
    if n < 2:
        return ""
    ymin = min(s.min(), b.min())
    ymax = max(s.max(), b.max())
    rng = (ymax - ymin) or 1.0

    def poly(arr, color, wid):
        pts = " ".join(
            f"{pad + (w - 2 * pad) * i / (n - 1):.1f},"
            f"{h - pad - (h - 2 * pad) * (v - ymin) / rng:.1f}"
            for i, v in enumerate(arr)
        )
        return f'<polyline fill="none" stroke="{color}" stroke-width="{wid}" points="{pts}"/>'

    base_y = h - pad - (h - 2 * pad) * (1.0 - ymin) / rng   # equity=1 基准线
    return f"""<svg viewBox="0 0 {w} {h}" style="width:100%;border:1px solid #eee;background:#fafafa">
  <line x1="{pad}" y1="{base_y:.1f}" x2="{w-pad}" y2="{base_y:.1f}" stroke="#ddd" stroke-dasharray="4"/>
  {poly(b, '#999', 1.5)}{poly(s, '#137333', 2)}
  <text x="{w-pad-4}" y="16" text-anchor="end" font-size="12" fill="#137333">■ 策略 Strategy</text>
  <text x="{w-pad-4}" y="32" text-anchor="end" font-size="12" fill="#999">■ 等权基准 Equal-weight</text>
</svg>"""


def _row(label, s_val, b_val, better: bool | None):
    mark = " class='win'" if better is True else (" class='lose'" if better is False else "")
    return f"<tr><td>{label}</td><td{mark}>{s_val}</td><td>{b_val}</td></tr>"


def generate_portfolio_report(strat: dict, bench: dict, sm: dict, bm: dict,
                              meta: dict) -> str:
    """生成组合报告 HTML,返回路径。| Generate the portfolio report HTML."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, "portfolio_report.html")

    beat_ret = sm["total_return"] > bm["total_return"]
    beat_sharpe = sm["sharpe"] > bm["sharpe"]
    smaller_dd = sm["max_drawdown"] > bm["max_drawdown"]   # 负数,更大=更浅
    if beat_ret and beat_sharpe:
        verdict = "✅ 组合在收益和风险调整后都赢过等权基准——信号选股确实加了分,值得继续验证。"
    elif smaller_dd and not beat_ret:
        verdict = "🟡 收益没赢过等权,但回撤更小——信号的价值在'避险/降波'而非'多赚'。"
    else:
        verdict = ("🔴 跑不赢「无脑等权持有整个池」——信号选股在组合层面没有加分。"
                   "诚实面对:这正是组合级回测的意义,它拦住了「以为选股有用其实没用」。")

    svg = _equity_svg(strat["equity"], bench["equity"])
    rows = (
        _row("总收益 %", sm["total_return"], bm["total_return"], beat_ret)
        + _row("年化收益 %", sm["ann_return"], bm["ann_return"], sm["ann_return"] > bm["ann_return"])
        + _row("夏普比率", sm["sharpe"], bm["sharpe"], beat_sharpe)
        + _row("最大回撤 %", sm["max_drawdown"], bm["max_drawdown"], smaller_dd)
        + _row("年化波动 %", sm["ann_vol"], bm["ann_vol"], sm["ann_vol"] < bm["ann_vol"])
        + f"<tr><td>累计成本拖累 %</td><td>{sm['total_cost']}</td><td>{bm['total_cost']}</td></tr>"
    )

    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>组合回测报告 Portfolio Backtest</title>
<style>
  body {{ font-family:-apple-system,"PingFang SC",sans-serif; max-width:820px;
         margin:40px auto; padding:0 20px; color:#222; line-height:1.6; }}
  h1 {{ font-size:22px; }} h2 {{ font-size:16px; margin-top:26px; }}
  table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:15px; }}
  th,td {{ border:1px solid #ddd; padding:8px 12px; text-align:right; }}
  th:first-child,td:first-child {{ text-align:left; }}
  th {{ background:#f5f5f7; }}
  .win {{ background:#e6f7ea; color:#137333; font-weight:600; }}
  .lose {{ background:#fdecea; color:#b3261e; }}
  .box {{ background:#fff8e1; border-left:4px solid #f4b400; padding:12px 16px;
         border-radius:4px; margin:16px 0; font-size:14px; }}
  .meta {{ color:#666; font-size:14px; }}
  .foot {{ color:#888; font-size:13px; margin-top:28px; border-top:1px solid #eee; padding-top:12px; }}
</style></head><body>
<h1>📦 组合回测报告 · Portfolio Backtest</h1>
<p class="meta">{meta['market'].upper()} · {meta['n_symbols']} 只 · 配置法 <b>{meta['method']}</b>
   (持仓 top-{meta['k']})· 每 {meta['rebalance']} 天再平衡 · 区间 {meta['period']}</p>

{svg}

<div class="box"><b>结论:</b>{verdict}</div>

<h2>策略 vs 等权基准</h2>
<table><tr><th>指标</th><th>信号组合</th><th>等权基准</th></tr>{rows}</table>

<div class="foot">
  基准=等权持有整个池(无脑分散)。战胜它才说明"信号选股"真加了分。<br>
  本报告用历史数据验证组合逻辑,不构成投资建议;含换手成本,未计冲击/滑点上限。
</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
