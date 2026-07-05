# -*- coding: utf-8 -*-
"""
home.py —— 统一主页(把所有产出串成一个入口)
home.py —— Unified home page (ties every output into one entry point)
=====================================================================
扫描 results/ 目录里已生成的东西(信号面板、可信度报告、个股报告),
生成一个带导航的 index.html——像个真产品的首页,点一下就进对应页面。
Scans the results/ folder for what's been generated (signal panel, credibility
report, per-stock reports) and builds a navigable index.html — a real product's
landing page where one click opens the matching page.
"""

from __future__ import annotations

import os

from quantmill import config

_RESULTS_DIR = config.RESULTS_DIR


def _exists(name: str) -> bool:
    return os.path.exists(os.path.join(_RESULTS_DIR, name))


def _card(href: str, icon: str, title: str, desc: str, ok: bool) -> str:
    """一张导航卡片;文件不存在时置灰并提示怎么生成。| A nav card; greyed out with a hint if the file is missing."""
    if ok:
        return (f'<a class="card" href="{href}"><div class="ic">{icon}</div>'
                f'<div class="t">{title}</div><div class="d">{desc}</div></a>')
    return (f'<div class="card off"><div class="ic">{icon}</div>'
            f'<div class="t">{title}</div><div class="d">{desc}</div>'
            f'<div class="hint">尚未生成</div></div>')


def generate_home() -> str:
    """生成 results/index.html,返回路径。| Generate results/index.html; return the path."""
    os.makedirs(_RESULTS_DIR, exist_ok=True)
    path = os.path.join(_RESULTS_DIR, "index.html")

    # 主功能卡片 | the main feature cards
    cards = [
        _card("dashboard.html", "📊", "自选股信号面板",
              "每只票今天该持有还是空仓 · 每天看一眼", _exists("dashboard.html")),
        _card("validation_report.html", "🔬", "策略可信度报告",
              "批量验证 + DSR/PBO:有优势还是运气+过拟合", _exists("validation_report.html")),
        _card("portfolio_report.html", "📦", "组合回测报告",
              "信号选股组合 vs 无脑等权基准,谁赢?", _exists("portfolio_report.html")),
    ]

    # 个股深度报告(动态列出 results/ 里所有 report_*.html)
    # Per-stock deep reports (dynamically list all report_*.html in results/)
    stock_reports = sorted(
        f for f in os.listdir(_RESULTS_DIR)
        if f.startswith("report_") and f.endswith(".html")
    )
    stock_links = "".join(
        f'<a class="chip" href="{f}">{f[len("report_"):-len(".html")]}</a>'
        for f in stock_reports
    ) or '<span class="none">还没有个股报告 —— 跑 <code>quant.py analyze</code> 生成</span>'

    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>quantmill · 量化研究工作台</title>
<style>
  body {{ font-family:-apple-system,"PingFang SC",sans-serif; max-width:820px;
         margin:40px auto; padding:0 20px; color:#222; }}
  h1 {{ font-size:24px; margin-bottom:4px; }}
  .sub {{ color:#666; font-size:14px; margin-bottom:24px; }}
  .grid {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .card {{ flex:1 1 240px; border:1px solid #e3e3e6; border-radius:12px;
          padding:20px; text-decoration:none; color:inherit; transition:.15s;
          background:#fff; }}
  .card:hover {{ box-shadow:0 4px 16px rgba(0,0,0,.08); transform:translateY(-2px);
               border-color:#c9c9cf; }}
  .card.off {{ opacity:.5; }}
  .ic {{ font-size:30px; }}
  .t {{ font-size:16px; font-weight:600; margin-top:10px; }}
  .d {{ font-size:13px; color:#666; margin-top:6px; line-height:1.5; }}
  .hint {{ font-size:12px; color:#b3261e; margin-top:8px; }}
  h2 {{ font-size:15px; margin-top:32px; color:#444; }}
  .chip {{ display:inline-block; margin:4px 6px 4px 0; padding:6px 12px;
          background:#f0f0f3; border-radius:20px; font-size:13px;
          text-decoration:none; color:#333; }}
  .chip:hover {{ background:#e0e0e6; }}
  .none {{ color:#999; font-size:13px; }}
  .foot {{ color:#999; font-size:12px; margin-top:40px; border-top:1px solid #eee;
          padding-top:12px; line-height:1.6; }}
  code {{ background:#f0f0f3; padding:1px 5px; border-radius:4px; }}
</style></head><body>
<h1>🛠️ quantmill · 量化研究工作台</h1>
<p class="sub">数据 → 特征 → 模型 → 回测 → 验证 → 面板 · 港股/美股/A股</p>

<div class="grid">{"".join(cards)}</div>

<h2>📈 个股深度报告 Per-stock reports</h2>
<div>{stock_links}</div>

<div class="foot">
  常用命令:<br>
  <code>python quant.py scan</code> —— 刷新自选股信号面板<br>
  <code>python quant.py validate</code> —— 跑批量可信度验证<br>
  <code>python quant.py analyze AAPL us</code> —— 深挖单只票<br>
  <code>python quant.py home</code> —— 刷新本页<br><br>
  提醒:本工作台的策略仅供研究,未通过可信度验证,别拿真钱跟。
</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


if __name__ == "__main__":
    p = generate_home()
    print(f"📄 主页已生成:{p}")
