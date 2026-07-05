# -*- coding: utf-8 -*-
"""
cli.py —— 统一命令入口(打包后暴露为 `quant` 命令)
cli.py —— Unified command entry (exposed as the `quant` command after install)
==============================================================================
子命令 / Subcommands:
    quant scan                刷新自选股信号面板 | refresh signal panel
    quant validate            批量可信度验证     | batch credibility check
    quant analyze AAPL us      深挖单只票         | deep-dive one stock
    quant home                 只刷新主页         | rebuild the home page

加 --quick 用小股票池快速试跑 | add --quick for a small, fast run
自选股在 watchlist.txt 里改   | edit your watchlist in watchlist.txt
每个命令跑完都会自动刷新主页 results/index.html。
Every command auto-refreshes the home page results/index.html when done.
"""

from __future__ import annotations

import argparse

from quantmill import config
from quantmill.report.home import generate_home


def _refresh_home():
    """跑完任何命令都刷新主页,让 index.html 始终最新。| Refresh home so index.html stays current."""
    path = generate_home()
    print(f"🏠 主页已更新:{path}")
    print("   用浏览器打开 results/index.html 即可进入工作台。")


def cmd_scan(a):
    from quantmill.report.dashboard import run
    from quantmill.credibility.validate import QUICK_UNIVERSE
    run(QUICK_UNIVERSE if a.quick else None,   # None -> 读 watchlist.txt | None -> read watchlist.txt
        start=a.start, end=a.end, horizon=a.horizon)
    _refresh_home()


def cmd_validate(a):
    from quantmill.credibility.validate import run_all, QUICK_UNIVERSE
    if a.quick:
        universe = QUICK_UNIVERSE
    else:
        from quantmill.watchlist import load_watchlist
        universe = load_watchlist()
    run_all(universe, start=a.start, end=a.end, horizon=a.horizon)
    _refresh_home()


def cmd_analyze(a):
    from quantmill.workflow.pipeline import run_single
    run_single(a.symbol, a.market, start=a.start, end=a.end, horizon=a.horizon,
               do_cv=not a.no_cv)
    _refresh_home()


def cmd_portfolio(a):
    from quantmill.portfolio import run_portfolio
    symbols = None
    if a.quick:
        from quantmill.watchlist import load_watchlist
        symbols = load_watchlist().get(a.market, [])[:3]
    run_portfolio(a.market, symbols=symbols, method=a.method, k=a.k,
                  start=a.start, end=a.end, horizon=a.horizon,
                  vol_target=a.vol_target)
    _refresh_home()


def cmd_news(a):
    from quantmill.llm.sentiment import news_sentiment
    res = news_sentiment(a.symbol, a.market, limit=a.limit)
    print("=" * 62)
    print(f"消息面情绪 · {a.market.upper()}:{a.symbol} · 打分器 {res['scorer']}")
    print("=" * 62)
    if res["n"] == 0:
        print("没抓到新闻(免费源新闻覆盖有限,尤其港/A股)。")
    else:
        mark = "🟢偏多" if res["mean"] > 0.1 else ("🔴偏空" if res["mean"] < -0.1 else "🟡中性")
        print(f"综合情绪 {res['mean']:+.2f} {mark}(近 {res['n']} 条)\n")
        for it in res["items"]:
            s = it.get("sentiment", 0.0)
            m = "🟢" if s > 0.1 else ("🔴" if s < -0.1 else "⚪")
            t = it["time"].date() if it.get("time") is not None else "?"
            print(f"  {m} {s:+.2f} [{t}] {it['title'][:64]}")
    print("\n⚠️ 情绪≠涨跌;LLM 只做情绪分类不预测价格;免费源无历史新闻→暂不能回测其 alpha,须过可信度层。")


def cmd_paper(a):
    from quantmill.execution.engine import paper_run, paper_status, paper_reset
    if a.action == "run":
        symbols = None
        if a.quick:
            from quantmill.watchlist import load_watchlist
            symbols = load_watchlist().get(a.market, [])[:3]
        try:
            paper_run(a.market, symbols=symbols, method=a.method, k=a.k,
                      horizon=a.horizon, broker_kind=a.broker)
        except (ImportError, RuntimeError) as e:
            print(f"\n[券商未就绪] {e}")
            print("提示:Alpaca 需 pip install -e \".[broker]\" 并设 "
                  "ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY;或用默认本地纸面(去掉 --broker)。")
    elif a.action == "status":
        paper_status()
    elif a.action == "reset":
        paper_reset(init_cash=a.cash)


def cmd_web(a):
    from quantmill.web.app import serve
    serve(port=a.port, open_browser=not a.no_open)


def cmd_cross(a):
    from quantmill.cross.run import run_ic, run_backtest, run_validate, run_survivorship
    if a.action == "ic":
        run_ic(market=a.market, quick=a.quick, horizon=a.horizon)
    elif a.action == "validate":
        run_validate(model=a.model, markets=("cn", "hk"), horizon=a.horizon, cost=a.cost)
    elif a.action == "survivorship":
        run_survivorship(market=a.market, model=a.model, k=a.topk, horizon=a.horizon, cost=a.cost)
    else:  # backtest
        run_backtest(market=a.market, quick=a.quick, k=a.topk, horizon=a.horizon,
                     cost=a.cost, long_short=a.long_short, model=a.model)


def cmd_docs_pdf(a):
    import os
    import subprocess
    from quantmill import config
    script = os.path.join(config.PROJECT_ROOT, "docs", "build_pdf.sh")
    if not os.path.exists(script):
        print(f"没找到构建脚本:{script}")
        return
    cmd = ["bash", script] + (["--no-open"] if a.no_open else [])
    raise SystemExit(subprocess.run(cmd).returncode)


def cmd_home(a):
    _refresh_home()


def cmd_factors(a):
    from quantmill.data import get_ohlcv
    from quantmill.factor.analysis import ic_report
    df = get_ohlcv(a.symbol, a.market, start=a.start, end=a.end)
    rep = ic_report(df, horizon=a.horizon)
    print("=" * 60)
    print(f"因子有效性排行 · {a.market.upper()}:{a.symbol} · 预测未来 {a.horizon} 天")
    print("IC=皮尔逊相关 · RankIC=秩相关(更稳健)· 日线单股 |RankIC|~0.1 已算不错")
    print("=" * 60)
    print(rep.head(15).to_string(index=False))
    print("\n⚠️ 单只高 IC ≠ 能赚钱:需多标的/多时段稳定,并过可信度层(DSR/PBO)。")


def main():
    p = argparse.ArgumentParser(
        prog="quantmill",
        description="quantmill 量化研究工作台 | quantmill research workbench")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--start", default=config.START)
        sp.add_argument("--end", default=None)
        sp.add_argument("--horizon", type=int, default=config.HORIZON)

    sp = sub.add_parser("scan", help="刷新自选股信号面板 | refresh signal panel")
    sp.add_argument("--quick", action="store_true", help="小股票池快速跑 | small, fast")
    add_common(sp)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("validate", help="批量可信度验证 | batch credibility check")
    sp.add_argument("--quick", action="store_true", help="小股票池快速跑 | small, fast")
    add_common(sp)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("analyze", help="深挖单只票 | deep-dive one stock")
    sp.add_argument("symbol", help="代码,如 AAPL / 00700 / 600519")
    sp.add_argument("market", choices=["us", "hk", "cn"], help="市场")
    sp.add_argument("--no-cv", action="store_true", help="跳过时序交叉验证(更快)")
    add_common(sp)
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("factors", help="因子有效性排行 IC/RankIC | factor IC ranking")
    sp.add_argument("symbol", help="代码,如 AAPL / 00700 / 600519")
    sp.add_argument("market", choices=["us", "hk", "cn"], help="市场")
    add_common(sp)
    sp.set_defaults(func=cmd_factors)

    sp = sub.add_parser("portfolio", help="组合回测 策略vs等权基准 | portfolio backtest")
    sp.add_argument("market", choices=["us", "hk", "cn"], help="单一市场 | single market")
    sp.add_argument("--method", default="topk",
                    choices=["topk", "invvol", "minvar", "equal"],
                    help="配置法:topk等权/invvol逆波动/minvar最小方差/equal等权")
    sp.add_argument("--k", type=int, default=None, help="持仓只数(默认一半)")
    sp.add_argument("--vol-target", type=float, default=None, dest="vol_target",
                    help="波动率目标(年化,如0.15):高波动时降仓避险")
    sp.add_argument("--quick", action="store_true", help="只用前3只快速跑 | first 3 names")
    add_common(sp)
    sp.set_defaults(func=cmd_portfolio)

    sp = sub.add_parser("news", help="消息面情绪 LLM打分近期新闻 | news sentiment")
    sp.add_argument("symbol", help="代码,如 AAPL / 00700 / 600519")
    sp.add_argument("market", choices=["us", "hk", "cn"], help="市场")
    sp.add_argument("--limit", type=int, default=12, help="抓多少条 | headline count")
    sp.set_defaults(func=cmd_news)

    sp = sub.add_parser("paper", help="纸面交易闭环 run/status/reset | paper trading")
    sp.add_argument("action", choices=["run", "status", "reset"])
    sp.add_argument("market", nargs="?", default="us", choices=["us", "hk", "cn"],
                    help="run 用的市场 | market for run")
    sp.add_argument("--method", default="topk",
                    choices=["topk", "invvol", "minvar", "equal"])
    sp.add_argument("--k", type=int, default=None, help="持仓只数")
    sp.add_argument("--cash", type=float, default=100_000, help="reset 的初始资金")
    sp.add_argument("--quick", action="store_true", help="run 只用前3只")
    sp.add_argument("--broker", default="paper", choices=["paper", "alpaca"],
                    help="paper本地模拟 / alpaca真券商纸面盘(需密钥)")
    sp.add_argument("--horizon", type=int, default=config.HORIZON)
    sp.set_defaults(func=cmd_paper)

    sp = sub.add_parser("cross", help="横截面选股:全市场排名+top-k回测 | cross-sectional selection")
    sp.add_argument("action", choices=["ic", "backtest", "validate", "survivorship"],
                    help="ic=因子排行 / backtest=选股回测 / validate=跨市场验证 / survivorship=量化前视偏差")
    sp.add_argument("--model", default="composite", choices=["composite", "ml"],
                    help="composite=稳健因子组合(默认,跨市场验证过)/ ml=LightGBM排名")
    sp.add_argument("--market", default="cn", choices=["cn", "hk", "us"])
    sp.add_argument("--quick", action="store_true", help="小股票池快速跑(10只)")
    sp.add_argument("-k", "--topk", type=int, default=20, help="持仓只数")
    sp.add_argument("--cost", type=float, default=0.0015, help="单边成本(默认0.15%)")
    sp.add_argument("--long-short", action="store_true", dest="long_short",
                    help="多空(买强卖弱;A股散户做空不现实,美股可)")
    sp.add_argument("--horizon", type=int, default=20, help="预测/持有天数")
    sp.set_defaults(func=cmd_cross)

    sp = sub.add_parser("web", help="启动网页仪表盘(实时行情)| launch web dashboard")
    sp.add_argument("--port", type=int, default=8787)
    sp.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    sp.set_defaults(func=cmd_web)

    sp = sub.add_parser("home", help="只刷新主页 | rebuild home page")
    sp.set_defaults(func=cmd_home)

    sp = sub.add_parser("docs-pdf", help="生成带UML渲染的文档PDF | build docs PDF with UML")
    sp.add_argument("--no-open", action="store_true", help="不自动打开")
    sp.set_defaults(func=cmd_docs_pdf)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
