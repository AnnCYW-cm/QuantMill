# -*- coding: utf-8 -*-
"""
model.py —— 横截面排名模型 | cross-sectional ranking model
=====================================================================
一个模型吃全市场面板,预测「同一天里每只票的相对强弱」。

关键工程纪律(这是本平台的护城河):
  1. **Purged walk-forward**:训练只用测试期之前的数据,且训练末尾砍掉 horizon 天
     ——因为标签 fwd 是「未来 horizon 天收益」,不砍就会偷看到测试期。
  2. **横截面归一化**:每个因子在「当天所有股票内」排成分位(0~1),
     让特征跨时间可比、去掉量纲——横截面建模的标准动作。
  3. **标签去市场**:target = fwd − 当天全市场均值,只留「相对」部分,
     不让模型把精力浪费在「大盘今天涨没涨」上。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def rank_normalize(panel: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """每个因子在同一天内排成分位(0~1),NaN 填 0.5(中性)。"""
    r = panel.groupby(level="date")[cols].rank(pct=True)
    return r.fillna(0.5)


def _demean(panel: pd.DataFrame, label: str) -> pd.Series:
    """标签去掉当天横截面均值,只留相对部分。"""
    y = panel[label]
    return y - y.groupby(level="date").transform("mean")


def walk_forward_scores(panel: pd.DataFrame, feature_cols: list[str],
                        label: str = "fwd", horizon: int = 20,
                        init_train: int = 504, step: int = 63,
                        params: dict | None = None) -> pd.Series:
    """Purged walk-forward,产出**样本外**打分 score(index = (date, symbol))。

    init_train 首个训练窗(交易日数),step 每隔多少天重训一次并预测下一段。
    """
    from lightgbm import LGBMRegressor

    # deterministic=True + force_row_wise=True:同机同输入可复现(可信度平台的底线)
    params = params or dict(n_estimators=300, learning_rate=0.03, num_leaves=31,
                            min_child_samples=80, subsample=0.8, colsample_bytree=0.8,
                            reg_lambda=1.0, random_state=0, n_jobs=-1, verbose=-1,
                            deterministic=True, force_row_wise=True)

    Xall = rank_normalize(panel, feature_cols)
    yall = _demean(panel, label)
    dates = panel.index.get_level_values("date").unique().sort_values()
    out = {}
    i = init_train
    n_fit = 0
    while i < len(dates):
        cut = dates[max(0, i - 1 - horizon)]          # 训练截止(已 purge horizon 天)
        test_lo, test_hi = dates[i], dates[min(i + step, len(dates)) - 1]

        tr_mask = panel.index.get_level_values("date") <= cut
        Xtr, ytr = Xall[tr_mask], yall[tr_mask]
        ok = ytr.notna() & Xtr.notna().all(axis=1)
        if ok.sum() < 500:                            # 训练样本太少就跳过这段
            i += step
            continue
        model = LGBMRegressor(**params)
        model.fit(Xtr[ok], ytr[ok])
        n_fit += 1

        te_mask = ((panel.index.get_level_values("date") >= test_lo) &
                   (panel.index.get_level_values("date") <= test_hi))
        Xte = Xall[te_mask]
        pred = pd.Series(model.predict(Xte), index=Xte.index)
        out.update(pred.to_dict())
        i += step

    print(f"[walk-forward] 重训 {n_fit} 次,样本外打分 {len(out)} 条")
    s = pd.Series(out, dtype=float).rename("score")
    if len(s):                                    # 恢复 (date, symbol) 索引名
        s.index = pd.MultiIndex.from_tuples(s.index, names=["date", "symbol"])
    return s
