# -*- coding: utf-8 -*-
"""
riskmodel.py —— 因子风险模型 + 绩效归因(共用一个引擎)
=====================================================================
引擎:逐日横截面 OLS 把收益回归到因子暴露(含截距=市场)→ 因子收益 + 特质收益。
  · 风险模型:因子收益协方差 F + 特质方差 D → 组合风险 = 因子风险 + 特质风险 + 各因子贡献
  · 绩效归因:组合因子暴露 × 因子收益 → 收益分解成 市场/各因子/特质

⚠️ 这是【统计型风格因子风险模型】(用平台自己的风格因子当暴露),不是完整 Barra;
   归因是"解释型"(用当期截面因子收益),量化研究足够,机构级另需商业风险模型。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quantmill.cross.model import rank_normalize


def factor_returns(panel: pd.DataFrame, factor_cols: list, ret_col: str = "fwd",
                   min_names: int = 10):
    """逐日横截面 OLS:ret ~ 1(市场) + 因子暴露。
    返回 (因子收益 fr[date × market+factors], 特质收益 specific[(date,symbol)])。"""
    X_all = rank_normalize(panel, factor_cols)
    y_all = panel[ret_col].astype(float)
    dates = panel.index.get_level_values("date").unique().sort_values()
    fr_rows, spec = {}, {}
    for d in dates:
        idx = panel.xs(d, level="date", drop_level=False).index
        y = y_all.loc[idx]
        X = X_all.loc[idx, factor_cols].astype(float)
        ok = y.notna() & X.notna().all(axis=1)
        if int(ok.sum()) < min_names:
            continue
        Xm = np.column_stack([np.ones(int(ok.sum())), X[ok.values].values])
        beta, *_ = np.linalg.lstsq(Xm, y[ok.values].values, rcond=None)
        resid = y[ok.values].values - Xm @ beta
        fr_rows[d] = beta
        for (dd, s), r in zip(idx[ok.values], resid):
            spec[(dd, s)] = r
    fr = pd.DataFrame.from_dict(fr_rows, orient="index",
                                columns=["market"] + list(factor_cols))
    fr.index.name = "date"
    specific = pd.Series(spec, name="specific")
    if len(specific):
        specific.index = pd.MultiIndex.from_tuples(specific.index, names=["date", "symbol"])
    return fr, specific


def factor_risk_model(panel: pd.DataFrame, factor_cols: list, ret_col: str = "fwd",
                      periods_per_year: float = 12.6) -> dict:
    """因子协方差 F(年化)+ 每票特质方差 D(年化)+ 池均值兜底。"""
    fr, specific = factor_returns(panel, factor_cols, ret_col)
    F = fr[factor_cols].cov() * periods_per_year
    spec_var = specific.groupby(level="symbol").var(ddof=1) * periods_per_year
    return {"factor_cov": F, "factor_ret": fr, "specific_var": spec_var,
            "avg_specific_var": float(spec_var.mean()) if len(spec_var) else 0.0}


def risk_decompose(weights: pd.Series, exposures: pd.DataFrame, model: dict) -> dict:
    """组合风险分解:总波动 = 因子波动 ⊕ 特质波动;并给各因子风险贡献。
    weights: symbol->w;exposures: symbol×factor(rank_normalize 后)。"""
    F = model["factor_cov"]
    fac = list(F.columns)
    syms = [s for s in weights.index if s in exposures.index]
    w = weights.loc[syms].to_numpy(float)
    B = exposures.loc[syms, fac].to_numpy(float)
    port_exp = B.T @ w                                    # 组合因子暴露
    fac_var = float(port_exp @ F.to_numpy() @ port_exp)
    sv = model["specific_var"].reindex(syms).fillna(model["avg_specific_var"]).to_numpy(float)
    spec_var = float((w ** 2 * sv).sum())
    total = float(np.sqrt(max(fac_var + spec_var, 0.0)))
    mc = port_exp * (F.to_numpy() @ port_exp)             # 各因子边际风险贡献(方差口径)
    contrib = pd.Series(mc / total if total > 0 else mc * 0, index=fac)
    return {"total_vol": total, "factor_vol": float(np.sqrt(max(fac_var, 0.0))),
            "specific_vol": float(np.sqrt(max(spec_var, 0.0))),
            "factor_contrib": contrib.sort_values(key=abs, ascending=False)}


def return_attribution(panel: pd.DataFrame, factor_cols: list,
                       picks_by_date: dict, ret_col: str = "fwd") -> pd.DataFrame:
    """把组合【超额收益】(相对等权池)分解成 各因子主动暴露贡献 + 选股(α)。

    用【主动暴露】= 组合暴露 − 全池平均暴露,乘以当期因子收益。剩下的是"选股"(选到了
    因子解释不了的好票=真 α)。归因超额而非总收益,避免市场基线导致的巨额抵消。
    picks_by_date: {date:[symbols]}。"""
    fr, _ = factor_returns(panel, factor_cols, ret_col)
    X = rank_normalize(panel, factor_cols)
    acc = {f: 0.0 for f in factor_cols}
    sel, total_active = 0.0, 0.0
    for d, syms in picks_by_date.items():
        if d not in fr.index:
            continue
        held = [s for s in syms if (d, s) in panel.index]
        if not held:
            continue
        Xd = X.xs(d, level="date")
        active = Xd.loc[held, factor_cols].mean() - Xd[factor_cols].mean()   # 主动暴露
        day = panel.xs(d, level="date")
        active_ret = float(day.loc[held, ret_col].mean() - day[ret_col].mean())
        explained = 0.0
        for f in factor_cols:
            c = float(active[f] * fr.loc[d, f])
            acc[f] += c
            explained += c
        sel += active_ret - explained
        total_active += active_ret
    acc["选股α"] = sel
    rows = [{"来源": k, "超额贡献%": round(v * 100, 2),
             "占比%": round(v / total_active * 100, 1) if abs(total_active) > 1e-9 else np.nan}
            for k, v in acc.items()]
    out = pd.DataFrame(rows).sort_values("超额贡献%", key=abs, ascending=False)
    out = pd.concat([out, pd.DataFrame([{"来源": "合计(超额)",
                                         "超额贡献%": round(total_active * 100, 2),
                                         "占比%": 100.0}])], ignore_index=True)
    return out
