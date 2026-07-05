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
    from quantmill.credibility.validate import QUICK_UNIVERSE
    from quantmill.report.dashboard import run
    run(QUICK_UNIVERSE if a.quick else None,   # None -> 读 watchlist.txt | None -> read watchlist.txt
        start=a.start, end=a.end, horizon=a.horizon)
    _refresh_home()


def cmd_validate(a):
    from quantmill.credibility.validate import QUICK_UNIVERSE, run_all
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
    from quantmill.execution.engine import paper_reset, paper_run, paper_status
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
    from quantmill.cross.run import run_backtest, run_ic, run_survivorship, run_validate
    if a.action == "ic":
        run_ic(market=a.market, quick=a.quick, horizon=a.horizon, sample=a.sample)
    elif a.action == "validate":
        run_validate(model=a.model, markets=("cn", "hk"), horizon=a.horizon, cost=a.cost)
    elif a.action == "survivorship":
        run_survivorship(market=a.market, model=a.model, k=a.topk, horizon=a.horizon, cost=a.cost)
    else:  # backtest
        run_backtest(market=a.market, quick=a.quick, k=a.topk, horizon=a.horizon,
                     cost=a.cost, long_short=a.long_short, model=a.model, sample=a.sample)


def cmd_experiment(a):
    from quantmill.workflow.experiment import (list_experiments, load_config,
                                               run_experiment, save_experiment)
    if a.exp_action == "list":
        exps = list_experiments()
        print("已存实验:" if exps else "还没有实验(先 run 一个)。")
        for e in exps:
            print("  ", e)
        return
    if not a.config:
        raise SystemExit("run 需要指定实验 YAML 路径,如:quantmill experiment run examples/experiments/sample_demo.yaml")
    cfg = load_config(a.config)
    print(f"跑实验:{cfg['name']} · {cfg['market']} · {cfg['model']} · "
          f"horizon={cfg['horizon']} k={cfg['k']}"
          + ("  (内置样本,离线)" if cfg["sample"] else ""))
    res = run_experiment(cfg)
    s = res["strat"]
    print("=" * 62)
    print(f"策略年化 {s['年化']}%  超额 {s['超额年化']}%  夏普 {s['夏普']}  "
          f"最大回撤 {s['最大回撤']}%  DSR {res['dsr']}  样本外{res['periods']}期  胜率{res['winrate']}%")
    print("=" * 62)
    if not a.no_save:
        print(f"结果已存档 -> {save_experiment(res)}")
    print("⚠️ 仅供研究,策略无经证实的 alpha,别拿真钱跟。")


def cmd_textfactor(a):
    from quantmill.llm.llm_client import backend
    from quantmill.llm.textfactor import combine, extract_signals
    if a.demo or not a.symbol:
        titles = ["公司季度业绩超预期,上调全年利润指引",
                  "遭监管立案调查,股价面临退市风险",
                  "宣布 10 亿元股票回购计划",
                  "第三季度营收低于市场预期,下调指引",
                  "召开年度股东大会审议分红方案"]
    else:
        from quantmill.llm.news import fetch_news
        titles = [it["title"] for it in fetch_news(a.symbol, a.market, limit=a.limit)]
        if not titles:
            print("没抓到新闻(免费源覆盖有限,尤其港/A股)。加 --demo 看离线演示。")
            return
    be = backend()
    sigs = extract_signals(titles, prefer_llm=True)
    print("=" * 74)
    print(f"LLM 文本因子抽取 · 后端 {be or '词典兜底(配 QUANTMILL_LLM_BASE_URL/MODEL/KEY 用 LLM)'}")
    print("=" * 74)
    print(f"{'展望':>6}{'指引':>6}{'风险':>6}{'因子':>7}  标题")
    for t, s in zip(titles, sigs):
        print(f"{s['outlook']:>+6.2f}{s['guidance']:>+6d}{s['risk']:>6.2f}{combine(s):>+7.2f}  {str(t)[:46]}")
    print("⚠️ 只抽取'文本说了什么'(分类),不预测涨跌;免费源无历史新闻→暂不能回测其 alpha,须过可信度层。")


def cmd_niche(a):
    from quantmill.niche import (analyze_cb_ipo, analyze_etf_premium,
                                 fetch_cb_first_days, fetch_etf_premium, load_sample_cb)
    if a.niche_action == "cb":
        df = load_sample_cb() if a.sample else fetch_cb_first_days(limit=a.limit)
        if df is None or len(df) == 0:
            print("拿不到可转债数据(本环境 eastmoney 常不通;你自己机器上应正常)。先试 --sample 看离线演示。")
            return
        r = analyze_cb_ipo(df, win_rate=a.win_rate)
        print("=" * 66)
        print(f"可转债打新 · 诚实验证{'(内置样本)' if a.sample else ''} · {r['n_bonds']} 只")
        print("=" * 66)
        print(f"📣 营销口径:首日均涨 {r['mean_first_day']}% · 涨超20%占 {r['pct_gain_20']}% · 破发率 {r['break_rate']}%")
        print(f"🧾 诚实口径(扣中签率 {a.win_rate*100:.3f}% · 顶格1000手):")
        print(f"   每只新债期望中签 {r['exp_hands_per_cb']} 手 → 期望收益 ≈ {r['ev_yuan_per_cb']} 元/账户")
        print(f"   👉 年化期望 ≈ {r['ev_yuan_per_year']:.0f} 元/账户(对中签率极敏感,用 --win-rate 填你的真实值)")
        if r.get("by_year"):
            print("   分年破发率/首日均值:")
            for y, v in sorted(r["by_year"].items()):
                print(f"     {y}: {v['n']}只 破发{v['break%']}% 均值{v['mean%']}%")
        print("⚠️ 首日翻卖≠持有到期(信用违约退市是独立尾部风险);要有意义需多账户;红利随中签率稀释、时效窗口短。")
    else:  # etf
        df = fetch_etf_premium()
        if df is None or len(df) == 0:
            print("拿不到 ETF 现价(本环境 eastmoney 常不通;你机器上应正常)。")
            return
        r = analyze_etf_premium(df, cost=a.cost)
        print("=" * 66)
        print(f"ETF 折溢价套利 · 当前横截面监控 · 全市场 {r['n_etf']} 只")
        print("=" * 66)
        print(f"平均 |折溢价| {r['mean_abs_premium']}%(中位 {r['median_abs_premium']}%)")
        print(f"扣往返成本 {a.cost*100:.2f}% 后,真够套利的:{r['n_exploitable']} 只({r['pct_over_cost']}%)")
        for t in r["top"]:
            print(f"     {t['code']} {t['name']}  折溢价{t['premium%']:+.2f}%  净{t['net%']:+.2f}%")
        print("⚠️ 最小申赎单位常几十万~上百万;停牌成分需现金替代;价差常在成本内;容量有限。")


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
    import logging
    # CLI 把库内 logging 打到 stdout(库被 import 时默认静默,不污染调用方)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
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
    sp.add_argument("--sample", action="store_true",
                    help="用随包内置小样本(20只×300天,离线秒出,装上即试)")
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

    sp = sub.add_parser("experiment", help="配置驱动的实验(YAML)run/list | config-driven experiments")
    sp.add_argument("exp_action", choices=["run", "list"], help="run=跑实验 / list=看已存实验")
    sp.add_argument("config", nargs="?", help="实验 YAML 路径(run 时必填)")
    sp.add_argument("--no-save", action="store_true", help="不存档结果")
    sp.set_defaults(func=cmd_experiment)

    sp = sub.add_parser("textfactor", help="LLM文本→结构化因子(展望/指引/风险)| LLM text->factor")
    sp.add_argument("symbol", nargs="?", help="代码(如 AAPL);省略或 --demo 用离线示例")
    sp.add_argument("market", nargs="?", default="us", choices=["us", "hk", "cn"])
    sp.add_argument("--demo", action="store_true", help="离线演示(内置示例标题)")
    sp.add_argument("--limit", type=int, default=10, help="抓多少条新闻")
    sp.set_defaults(func=cmd_textfactor)

    sp = sub.add_parser("niche", help="散户结构性机会验证:可转债打新/ETF套利 | retail niche edges")
    sp.add_argument("niche_action", choices=["cb", "etf"], help="cb=可转债打新 / etf=ETF折溢价")
    sp.add_argument("--sample", action="store_true", help="cb:用内置合成样本(离线秒出)")
    sp.add_argument("--limit", type=int, default=None, help="cb:只拉前N只(试跑)")
    sp.add_argument("--win-rate", type=float, default=0.00003, dest="win_rate",
                    help="cb:单账户每手中签率(默认0.003%,对结果极敏感,请填你的真实值)")
    sp.add_argument("--cost", type=float, default=0.002, help="etf:往返成本(默认0.2%)")
    sp.set_defaults(func=cmd_niche)

    sp = sub.add_parser("docs-pdf", help="生成带UML渲染的文档PDF | build docs PDF with UML")
    sp.add_argument("--no-open", action="store_true", help="不自动打开")
    sp.set_defaults(func=cmd_docs_pdf)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
