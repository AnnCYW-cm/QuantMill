# -*- coding: utf-8 -*-
"""
experiment.py —— 配置驱动的横截面实验 + 追踪 | config-driven experiments & tracking
=====================================================================
一个 YAML 定义一次实验(市场 / 因子配方 / 模型 / 参数 / 日期),可复现地跑,
结果自动存档到 results/experiments/<时间戳>_<名字>/,便于对比与复现。
对标 Qlib 的 workflow,但更轻:不用改代码就能换因子/参数做研究。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import pandas as pd
import yaml

from quantmill import config

# 可配置项与默认值(YAML 里只需写想改的)| configurable keys + defaults
DEFAULTS: dict = {
    "name": "unnamed",
    "market": "cn",          # cn / hk / us
    "model": "composite",    # composite(稳健组合) / ml(LightGBM)
    "horizon": 20,           # 预测/持有天数
    "k": 20,                 # 持仓只数(会按股票池大小自动收窄)
    "cost": 0.0015,          # 单边成本
    "sample": False,         # True=用随包小样本(离线)
    "start": None,           # 数据起始日(None=默认)
    "recipe": None,          # composite 因子配方覆盖(dict,可选)
    "init_train": 504,       # ml 首个训练窗
    "step": 63,              # ml 重训步长
}


def load_config(path: str) -> dict:
    """读 YAML 实验配置,只保留已知键,其余用默认。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in raw.items() if k in DEFAULTS})
    return cfg


def run_experiment(cfg: dict) -> dict:
    """按配置跑一次横截面实验,返回结构化结果清单(不落盘)。"""
    from quantmill.credibility.stats import deflated_sharpe_ratio, sharpe
    from quantmill.cross import (composite_score, factor_columns, get_panel,
                                 ic_table, topk_backtest, walk_forward_scores)

    c = dict(DEFAULTS)
    c.update(cfg or {})
    panel = get_panel(market=c["market"], sample=c["sample"], horizon=c["horizon"],
                      start=c["start"], verbose=False)
    cols = factor_columns(panel)
    n_uni = panel.index.get_level_values(1).nunique()
    n_dates = panel.index.get_level_values(0).nunique()
    k = min(int(c["k"]), max(2, n_uni // 3))            # 小池自动收窄

    if c["model"] == "composite":
        score = composite_score(panel, recipe=c["recipe"])
    else:
        it = min(int(c["init_train"]), max(60, n_dates // 2))
        score = walk_forward_scores(panel, cols, horizon=c["horizon"],
                                    init_train=it, step=int(c["step"]))

    res = topk_backtest(panel, score, k=k, horizon=c["horizon"], cost=c["cost"])
    eq = res["equity"]
    strat, bench = res["metrics"]["策略 top-k"], res["metrics"]["基准 等权"]

    dsr = None
    if len(eq) > 3:
        kks = sorted({x for x in (max(2, k // 2), k) if 2 * x + 5 <= n_uni})
        trials = [sharpe(topk_backtest(panel, score, k=kk, horizon=c["horizon"],
                                       cost=c["cost"])["equity"]["long"]) for kk in kks]
        if trials:
            dsr = round(float(deflated_sharpe_ratio(
                eq["long"], sr_trials=trials, n_trials=max(len(trials), 10))["dsr"]), 3)

    return {
        "config": c, "k_used": k, "universe": int(n_uni), "periods": int(len(eq)),
        "start": str(eq.index[0].date()) if len(eq) else None,
        "end": str(eq.index[-1].date()) if len(eq) else None,
        "strat": strat, "bench": bench, "dsr": dsr,
        "winrate": round(float((eq["long"] > eq["bench"]).mean() * 100), 1) if len(eq) else None,
        "ic": ic_table(panel, cols).head(10).to_dict("records"),
        "equity": [{"date": str(d.date()), "strat": round(float(s), 5), "bench": round(float(b), 5)}
                   for d, s, b in zip(eq.index, (1 + eq["long"]).cumprod(),
                                      (1 + eq["bench"]).cumprod())],
    }


def save_experiment(result: dict) -> str:
    """把实验结果存档到 results/experiments/<时间戳>_<名字>/(config/result/equity/ic)。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = str(result["config"].get("name", "unnamed"))
    outdir = os.path.join(config.RESULTS_DIR, "experiments", f"{ts}_{name}")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(result["config"], f, allow_unicode=True, sort_keys=False)
    manifest = {k: v for k, v in result.items() if k != "equity"}
    with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    pd.DataFrame(result["equity"]).to_csv(os.path.join(outdir, "equity.csv"), index=False)
    pd.DataFrame(result["ic"]).to_csv(os.path.join(outdir, "ic.csv"), index=False)
    return outdir


def list_experiments() -> list[str]:
    base = os.path.join(config.RESULTS_DIR, "experiments")
    return sorted(os.listdir(base)) if os.path.isdir(base) else []
