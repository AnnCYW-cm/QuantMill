"""
analysis.py —— 因子有效性分析(IC / RankIC / 分位单调性)| Factor analysis
=========================================================================
造出因子后,得问一句:它到底能不能预测未来收益?用 IC 量化。
After building a factor, ask: does it actually predict forward returns? Quantify with IC.

  IC (Information Coefficient)  = 因子值与未来收益的相关系数(Pearson)
  RankIC                        = 秩相关(Spearman),对异常值稳健,更常用
  分位单调性                     = 按因子分 5 档,看未来收益是否单调递增(有效因子应单调)

⚠️ 呼应可信度层:单个高 IC 不等于能赚钱;要多标的、多时段稳定,且警惕过拟合。
   A high IC on one stock ≠ money. Needs to hold across names/periods (see credibility layer).
"""

from __future__ import annotations

import pandas as pd

from quantmill import config
from quantmill.factor.library import compute_factors


def forward_return(df: pd.DataFrame, horizon: int = config.HORIZON) -> pd.Series:
    """未来 horizon 天的收益率(用于评估因子;⚠️含未来,仅供分析不喂模型特征)。
    Forward return over horizon days (for evaluation only; contains the future)."""
    return df["Close"].shift(-horizon) / df["Close"] - 1


def factor_ic(factor: pd.Series, fwd: pd.Series) -> tuple[float, float]:
    """单个因子 vs 未来收益的 (IC 皮尔逊, RankIC 斯皮尔曼)。| (Pearson IC, Spearman RankIC)."""
    s = pd.concat([factor.rename("f"), fwd.rename("r")], axis=1).dropna()
    if len(s) < 10 or s["f"].std() == 0:
        return float("nan"), float("nan")
    ic = s["f"].corr(s["r"])
    ric = s["f"].corr(s["r"], method="spearman")
    return float(ic), float(ric)


def ic_report(df: pd.DataFrame, horizon: int = config.HORIZON,
              names=None) -> pd.DataFrame:
    """
    对因子库里每个因子算 IC/RankIC,按 |RankIC| 从高到低排序。
    Compute IC/RankIC for each factor, sorted by |RankIC| descending.
    返回列:factor, IC, RankIC, absRankIC
    """
    fwd = forward_return(df, horizon)
    factors = compute_factors(df, names)
    rows = []
    for name in factors.columns:
        ic, ric = factor_ic(factors[name], fwd)
        rows.append({"factor": name, "IC": round(ic, 4), "RankIC": round(ric, 4),
                     "absRankIC": round(abs(ric), 4) if ric == ric else float("nan")})
    rep = pd.DataFrame(rows)
    return rep.sort_values("absRankIC", ascending=False,
                           na_position="last").reset_index(drop=True)


def quantile_returns(factor: pd.Series, fwd: pd.Series, q: int = 5) -> pd.Series:
    """
    按因子值分 q 档,返回每档的平均未来收益。有效因子应大致单调(高档收益高)。
    Bucket by factor value into q groups; return mean forward return per bucket.
    A useful factor should be roughly monotonic across buckets.
    """
    s = pd.concat([factor.rename("f"), fwd.rename("r")], axis=1).dropna()
    if len(s) < q * 2:
        return pd.Series(dtype=float)
    # 用 rank 分箱避免重复值报错 | rank-based binning to avoid duplicate-edge errors
    s["bucket"] = pd.qcut(s["f"].rank(method="first"), q, labels=False)
    return s.groupby("bucket")["r"].mean()


if __name__ == "__main__":
    from quantmill.data import get_ohlcv

    df = get_ohlcv("AAPL", "us", start="2018-01-01", end="2024-01-01")
    rep = ic_report(df, horizon=5)
    print("因子有效性排行(按 |RankIC|,前12):")
    print(rep.head(12).to_string(index=False))
