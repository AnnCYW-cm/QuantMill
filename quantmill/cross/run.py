"""
run.py —— 横截面流水线编排 | cross-sectional pipeline orchestration
=====================================================================
把 universe → panel → ic / model+backtest → 可信度 串起来,给 CLI 和网页调用。
面板按市场缓存到 data/panel_<market>.pkl,避免每次重拉全池。
"""
from __future__ import annotations

import logging
import os
import time

import pandas as pd

logger = logging.getLogger(__name__)
_PANEL_STALE_DAYS = 7          # 面板缓存超过这么多天就提醒可能陈旧 | staleness warning threshold

from quantmill import config
from quantmill.cross.backtest import topk_backtest
from quantmill.cross.ic import ic_decay, ic_table
from quantmill.cross.model import walk_forward_scores
from quantmill.cross.panel import build_panel, factor_columns
from quantmill.cross.universe import universe

DEFAULT_START = "2023-01-01"     # 与百度估值「近三年」对齐 | aligned with valuation history


def load_sample_panel() -> pd.DataFrame:
    """随包发布的小样本面板(20只A股×300天),装上即试、无需联网。
    Bundled tiny sample panel (20 A-shares × 300 days) — works offline out of the box."""
    from importlib.resources import files
    res = files("quantmill.data").joinpath("sample", "panel_sample.csv.gz")
    with res.open("rb") as f:
        panel = pd.read_csv(f, index_col=[0, 1], parse_dates=[0], compression="gzip")
    panel.index.names = ["date", "symbol"]
    return panel


def get_panel(market: str = "cn", quick: bool = False, n: int | None = None,
              start: str | None = None, horizon: int = 20, refresh: bool = False,
              verbose: bool = True, sample: bool = False) -> pd.DataFrame:
    """建/取横截面面板;全池会缓存到 data/panel_<market>.pkl。sample=True 用随包小样本(离线)。"""
    if sample:
        logger.info("[cross] 使用内置样本面板(20只×300天,离线)。真实全池请去掉 --sample。")
        return load_sample_panel()
    start = start or DEFAULT_START
    cache = os.path.join(config.DATA_DIR, f"panel_{market}.pkl")
    full = not quick and n is None
    if full and not refresh and os.path.exists(cache):
        age_days = (time.time() - os.path.getmtime(cache)) / 86400
        if age_days > _PANEL_STALE_DAYS:
            logger.warning(f"[cross] ⚠️ 面板缓存已 {age_days:.0f} 天,可能陈旧;"
                           f"加 --refresh(或删 {os.path.basename(cache)})重建。")
        logger.info(f"[cross] 复用缓存面板 {cache}")
        return pd.read_pickle(cache)
    syms = universe(market, n=(10 if quick else n))
    logger.info(f"[cross] {market} 股票池 {len(syms)} 只,构建面板(start={start}, horizon={horizon})…")
    panel = build_panel(syms, market=market, start=start, horizon=horizon, verbose=verbose)
    if full:
        panel.to_pickle(cache)
        logger.info(f"[cross] 面板已缓存 -> {cache}")
    return panel


def run_ic(market: str = "cn", quick: bool = False, horizon: int = 20,
           top: int = 20, **kw) -> pd.DataFrame:
    """横截面 IC 排行。| cross-sectional IC ranking."""
    panel = get_panel(market=market, quick=quick, horizon=horizon, **kw)
    tab = ic_table(panel, factor_columns(panel))
    print("\n" + "=" * 66)
    print(f"横截面 RankIC 排行 · {market.upper()} · {panel.index.get_level_values(1).nunique()} 只 · "
          f"预测未来 {horizon} 天(横向选股,|IC| 越大越能区分强弱)")
    print("⚠️ 单因子 |IC| 0.03~0.05 已算可用;ICIR>0.3 较稳;t 因区间重叠偏高,仅参考")
    print("=" * 66)
    print(tab.head(top).to_string(index=False))
    return tab


def run_ic_decay(market: str = "cn", quick: bool = False, sample: bool = False,
                 factor: str | None = None, horizons=(1, 2, 3, 5, 10, 20),
                 top_factors: int = 10, **kw) -> pd.DataFrame:
    """IC 衰减:因子×horizon 的横截面 IC 矩阵,看信号多快衰减(决定换仓频率)。"""
    if sample:                                      # 样本面板不带 close → 提示走真实池
        raise SystemExit("ic-decay 需要带价面板(keep_close),--sample 不支持;去掉 --sample 用真实池(可加 --quick)。")
    syms = universe(market, n=(10 if quick else None))
    logger.info(f"[ic-decay] {market} {len(syms)} 只,构建带价面板…")
    panel = build_panel(syms, market=market, start=DEFAULT_START, keep_close=True, verbose=False)
    cols = [factor] if factor else factor_columns(panel)
    mat = pd.DataFrame({f: dict(zip((f"h{h}" for h in horizons),
                                    ic_decay(panel, f, horizons=horizons)["IC"]))
                        for f in cols}).T
    mat = mat.reindex(mat.iloc[:, 0].abs().sort_values(ascending=False).index).head(top_factors)
    print("\n" + "=" * 66)
    print(f"IC 衰减矩阵 · {market.upper()} · {panel.index.get_level_values(1).nunique()} 只 · "
          f"因子×未来h天横截面 IC(按 |h{horizons[0]}| 排序)")
    print("👉 从左到右快速衰减=短线信号,要勤换仓;衰减慢=中长线,换仓可稀。")
    print("=" * 66)
    print(mat.round(4).to_string())
    return mat


def run_riskmodel(market: str = "cn", quick: bool = False, sample: bool = False,
                  horizon: int = 20, top: int = 20, **kw) -> dict:
    """因子风险模型:因子波动 + 当前 top-k 组合的风险分解(因子 vs 特质 + 各因子贡献)。"""
    from quantmill.cross.composite import composite_score
    from quantmill.cross.model import rank_normalize
    from quantmill.cross.riskmodel import factor_risk_model, risk_decompose
    panel = get_panel(market=market, quick=quick, sample=sample, horizon=horizon, **kw)
    cols = factor_columns(panel)
    ppy = 252.0 / horizon
    m = factor_risk_model(panel, cols, periods_per_year=ppy)
    score = composite_score(panel)
    d = panel.index.get_level_values("date").unique()[-1]
    exp = rank_normalize(panel, cols).xs(d, level="date")
    sc = score[score.index.get_level_values("date") == d]
    sc.index = sc.index.get_level_values("symbol")
    held = sc.sort_values(ascending=False).head(top).index
    w = pd.Series(1 / len(held), index=held)
    r = risk_decompose(w, exp, m)
    print("\n" + "=" * 66)
    print(f"因子风险模型 · {market.upper()} · 当前 top-{len(held)} 组合(年化口径)")
    print("=" * 66)
    print(f"总波动 {r['total_vol']*100:.1f}%  =  因子 {r['factor_vol']*100:.1f}%  ⊕  特质 {r['specific_vol']*100:.1f}%")
    print("各因子风险贡献(方差口径,绝对值大=风险来源):")
    print((r["factor_contrib"] * 100).round(2).to_string())
    print("⚠️ 统计型风格因子风险模型(非完整 Barra);机构级另需商业风险模型。")
    return {"model": m, "decomp": r}


def run_attribution(market: str = "cn", quick: bool = False, sample: bool = False,
                    horizon: int = 20, k: int = 20, cost: float = 0.0015,
                    model: str = "composite", **kw) -> pd.DataFrame:
    """绩效归因:把 top-k 组合的累计收益分解成 市场 / 各因子 / 特质。"""
    from quantmill.cross.riskmodel import return_attribution
    panel = get_panel(market=market, quick=quick, sample=sample, horizon=horizon, **kw)
    cols = factor_columns(panel)
    score = _score_for(panel, cols, model, horizon, min(504, len(panel) // 2), 63)
    res = topk_backtest(panel, score, k=k, horizon=horizon, cost=cost)
    att = return_attribution(panel, cols, res["picks"])
    print("\n" + "=" * 66)
    print(f"绩效归因 · {market.upper()} · {model} top-{k} · 收益从哪来")
    print("=" * 66)
    print(att.to_string(index=False))
    print("👉 特质占比高=靠选股(α);某因子占比高=其实在吃那个因子的 β(风格暴露)。")
    return att


def run_neutralize(market: str = "cn", quick: bool = False, sample: bool = False,
                   horizon: int = 20, by=("size",), **kw) -> pd.DataFrame:
    """因子中性化前后对比:各因子横截面 IC(原始 vs 对 size 中性化后)。"""
    from quantmill.cross.ic import ic_summary
    from quantmill.cross.neutralize import neutralize
    panel = get_panel(market=market, quick=quick, sample=sample, horizon=horizon, **kw)
    cols = [c for c in factor_columns(panel) if c not in by]
    rows = []
    for f in cols:
        ic0 = ic_summary(panel, f)["IC"]
        p2 = panel.assign(_n=neutralize(panel, f, by=by))
        ic1 = ic_summary(p2, "_n")["IC"]
        rows.append({"factor": f, "IC原始": ic0, f"IC中性化({'+'.join(by)})": ic1,
                     "IC变化": round((ic1 or 0) - (ic0 or 0), 4)})
    tab = pd.DataFrame(rows)
    print("\n" + "=" * 66)
    print(f"因子中性化对比 · {market.upper()} · 对 {'+'.join(by)} 中性化")
    print("=" * 66)
    print(tab.to_string(index=False))
    print("👉 中性化后 IC 大降的因子,原来多半是市值/行业的替身,不是独立 α。")
    return tab


def _score_for(panel, cols, model, horizon, init_train, step):
    """按 model 产出打分:composite=固定配方零训练;ml=walk-forward LightGBM。"""
    if model == "composite":
        from quantmill.cross.composite import composite_score
        return composite_score(panel)
    return walk_forward_scores(panel, cols, horizon=horizon,
                               init_train=init_train, step=step)


def run_backtest(market: str = "cn", quick: bool = False, k: int = 20,
                 horizon: int = 20, init_train: int = 504, step: int = 63,
                 cost: float = 0.0015, long_short: bool = False,
                 model: str = "composite", credibility: bool = True, **kw) -> dict:
    """横截面策略回测 + DSR 可信度。model: composite=稳健因子组合(默认,跨市场验证过)/ ml=LightGBM。"""
    from quantmill.credibility.stats import deflated_sharpe_ratio

    panel = get_panel(market=market, quick=quick, horizon=horizon, **kw)
    cols = factor_columns(panel)
    n_uni = panel.index.get_level_values(1).nunique()
    n_dates = panel.index.get_level_values(0).nunique()
    k = min(k, max(2, n_uni // 3))          # 小股票池自动收窄持仓,避免 top-k≈全池
    init_train = min(init_train, max(60, n_dates // 2))   # 小样本收窄训练窗
    score = _score_for(panel, cols, model, horizon, init_train, step)
    res = topk_backtest(panel, score, k=k, horizon=horizon,
                        cost=cost, long_short=long_short)
    name = "稳健因子组合" if model == "composite" else "ML排名(LightGBM)"
    print("\n" + "=" * 66)
    print(f"横截面策略回测 · {market.upper()} · {name} · top-{k} · 每 {horizon} 天换仓 · "
          f"成本 {cost*100:.2f}% · {'多空' if long_short else '纯多头'}")
    print("=" * 66)
    print(pd.DataFrame(res["metrics"]).T.to_string())

    eq = res["equity"]
    print(f"\n样本外 {len(eq)} 期  {eq.index[0].date()} ~ {eq.index[-1].date()}  "
          f"胜基准期数 {(eq['long'] > eq['bench']).mean()*100:.0f}%")

    if credibility and len(eq) > 3:
        # DSR:用不同 k 当尝试基准,扣多重检验 | DSR corrected for a small k-search
        trials = []
        for kk in (10, 20, 30, 50):
            r = topk_backtest(panel, score, k=kk, horizon=horizon, cost=cost)
            from quantmill.credibility.stats import sharpe
            trials.append(sharpe(r["equity"]["long"]))
        dsr = deflated_sharpe_ratio(eq["long"], sr_trials=trials, n_trials=max(len(trials), 20))
        print(f"\n[可信度] DSR = {dsr['dsr']:.3f}  (P(真夏普>0),>0.95 才算扣多重检验后显著)")
        print("          ⚠️ 幸存者偏差未修(用当前成分股)—— 别把回测收益当真实 alpha。")
        res["dsr"] = dsr
    return res


def _auto_k(n: int) -> int:
    """按股票池大小自动定持仓数(池大多持、池小少持)。"""
    return int(min(20, max(8, n // 7)))


def run_validate(model: str = "composite", markets=("cn", "hk"), horizon: int = 20,
                 cost: float = 0.0015, init_train: int = 504, step: int = 63, **kw) -> list:
    """跨市场验证:同一套方法在多个市场各跑一遍,看超额是否都为正(稳健性)。"""
    rows = []
    for mk in markets:
        panel = get_panel(market=mk, horizon=horizon, verbose=False, **kw)
        cols = factor_columns(panel)
        n = panel.index.get_level_values(1).nunique()
        k = _auto_k(n)
        score = _score_for(panel, cols, model, horizon, init_train, step)
        m = topk_backtest(panel, score, k=k, horizon=horizon, cost=cost)["metrics"]["策略 top-k"]
        rows.append({"market": mk.upper(), "universe": n, "k": k,
                     "excess": m["超额年化"], "sharpe": m["夏普"], "mdd": m["最大回撤"]})
    name = "稳健因子组合" if model == "composite" else "ML排名(LightGBM)"
    print("\n" + "=" * 66)
    print(f"跨市场验证 · {name} · 同一套方法在不同市场")
    print("=" * 66)
    print(f"{'市场':<6}{'股票池':>7}{'k':>5}{'超额年化%':>11}{'夏普':>7}{'最大回撤%':>11}")
    for r in rows:
        print(f"{r['market']:<6}{r['universe']:>7}{r['k']:>5}{r['excess']:>11.1f}{r['sharpe']:>7.2f}{r['mdd']:>11.1f}")
    allpos = all(r["excess"] > 0 for r in rows)
    print("\n" + ("✅ 所有市场超额均为正 —— 跨市场稳健(简单组合的价值所在)"
                  if allpos else "🔴 有市场为负 —— 未能跨市场复现"))
    return rows


def run_survivorship(market: str = "cn", model: str = "composite", k: int = 20,
                     horizon: int = 20, cost: float = 0.0015, **kw) -> dict:
    """量化前视/幸存者偏差:全池 vs PIT(起点前已纳入)对比。仅 A股(靠纳入日期)。"""
    from quantmill.cross.universe import csi300_pit
    panel = get_panel(market=market, horizon=horizon, verbose=False, **kw)
    cols = factor_columns(panel)
    pit = set(csi300_pit())
    if not pit:
        print("[survivorship] PIT 名单不可用(仅支持 A股)。")
        return {}
    pit_panel = panel[panel.index.get_level_values("symbol").isin(pit)]

    def _bt(p):
        sc = _score_for(p, cols, model, horizon, 504, 63)
        return topk_backtest(p, sc, k=k, horizon=horizon, cost=cost)["metrics"]["策略 top-k"]

    a, b = _bt(panel), _bt(pit_panel)
    fn = panel.index.get_level_values("symbol").nunique()
    pn = pit_panel.index.get_level_values("symbol").nunique()
    name = "稳健因子组合" if model == "composite" else "ML排名(LightGBM)"
    print("\n" + "=" * 66)
    print(f"前视/幸存者偏差量化 · {market.upper()} · {name}")
    print("=" * 66)
    print(f"  全池 {fn} 只(含前视污染) : 超额年化 {a['超额年化']:+.1f}%  夏普 {a['夏普']}")
    print(f"  PIT {pn} 只(2023前已纳入): 超额年化 {b['超额年化']:+.1f}%  夏普 {b['夏普']}")
    bias = round(a["超额年化"] - b["超额年化"], 1)
    print(f"  → 前视偏差贡献: {bias:+.1f}% 年化"
          f"{'(去污染反而更好=不依赖偏差)' if bias < 0 else '(去污染就崩=严重依赖偏差)'}")
    print("  ⚠️ PIT 仅修「前视纳入」这一半;「起点在后被踢出」的股票仍缺,需付费数据。")
    return {"full": a, "pit": b, "bias": bias, "full_n": fn, "pit_n": pn}
