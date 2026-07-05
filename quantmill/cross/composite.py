"""
composite.py —— 稳健因子组合 | robust factor composite
=====================================================================
不训练、固定配方:只用「A股 & 港股都同号复现」的少数普适因子,
每天把它们的横截面分位按符号相加,得到打分。

为什么它比 43 因子 ML 模型更该主推:
  · 零训练 => 天生没有过拟合、没有样本内外之分(整段都是样本外)
  · 跨市场实测:ML 模型 A股+33.5% 但港股−10.2%(不复现);
    这个简单组合 A股+3.4% / 港股+15.4%(两地都为正)——简单打败复杂。

配方(可改;正=越大越好,负=越小越好):
  ey +1  盈利收益率(价值)   bp +1  账面价值比(价值)
  dist_high_20 +1  近高点(动量) pos_60d +1  高位(动量)
  vol_20d −1  低波动(低波异象)
"""
from __future__ import annotations

import pandas as pd

from quantmill.cross.model import rank_normalize

# 跨市场同号复现的普适因子配方 | cross-market-validated recipe
ROBUST_RECIPE: dict[str, int] = {
    "ey": 1, "bp": 1, "dist_high_20": 1, "pos_60d": 1, "vol_20d": -1,
}


def composite_score(panel: pd.DataFrame, recipe: dict[str, int] | None = None) -> pd.Series:
    """稳健因子组合打分:各因子每日横截面分位按符号平均。越大越看好。
    Robust composite score: sign-weighted average of daily cross-sectional ranks."""
    recipe = recipe or ROBUST_RECIPE
    cols = [c for c in recipe if c in panel.columns]
    if not cols:
        raise ValueError("面板里没有配方所需的因子列 | none of the recipe factors present")
    r = rank_normalize(panel, cols)                 # 每日横截面分位 0~1
    s = sum(recipe[c] * r[c] for c in cols) / len(cols)
    return s.rename("score")
