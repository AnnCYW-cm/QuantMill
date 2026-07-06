"""
model.py —— LightGBM 涨跌预测 + 时序交叉验证(Day 6 核心)
model.py — LightGBM up/down prediction + time-series cross-validation (Day 6 core)
=========================================================
模型吃"今天的特征",吐出 P(未来会涨) 的概率,这个概率就是交易信号。
The model takes in "today's features" and outputs P(price will rise), and that probability is the trading signal.

三个能力:
Three capabilities:
  1. time_series_cv    —— 用向前滚动的方式诚实评估模型准不准(超过基准才有戏)
                          honestly evaluate model accuracy via forward-rolling (only worthwhile if it beats the baseline)
  2. walk_forward      —— 生成【样本外】预测概率序列,给回测用(绝不偷看未来)
                          generate an [out-of-sample] predicted-probability series for backtesting (never peek at the future)
  3. train_full        —— 用全部数据训一个模型(看特征重要性 / 给未来一天做预测)
                          train one model on all the data (inspect feature importance / predict for a future day)

铁律:时间只能往前走。永远拿【过去】训练、预测【未来】。
Iron rule: time only moves forward. Always train on the [past] and predict the [future].
      任何"打乱后交叉验证"在时序问题里都是未来函数,直接作废。
      Any "shuffled cross-validation" is a look-ahead function in time-series problems and is invalid outright.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import TimeSeriesSplit

from quantmill import config
from quantmill.factor import FEATURE_COLS
from quantmill.model.models import make_lgbm_classifier
from quantmill.model.provider import resolve_classifier


def _make_model() -> LGBMClassifier:
    """单股分类器(浅树+强正则防过拟合)。参数在 model.models,这里保持原名供 train_full 用。
    A deliberately restrained LightGBM (shallow trees + strong regularization)."""
    return make_lgbm_classifier()


def time_series_cv(X: pd.DataFrame, y: pd.Series, n_splits: int = config.N_SPLITS) -> dict:
    """
    时序交叉验证:把时间切成 n_splits 段,逐段"拿前面训练、测后面一段"。
    Time-series cross-validation: split time into n_splits segments, and for each "train on the earlier part, test on the following segment".
    对比模型准确率 vs 基准(永远猜多数类)。基准都赢不了 = 模型没学到东西。
    Compare model accuracy vs the baseline (always guess the majority class). Can't even beat the baseline = the model learned nothing.
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    accs, base_accs = [], []
    print(f"\n{'折':>3} {'训练样本':>8} {'测试样本':>8} {'模型准确率':>10} {'基准':>8}")
    print("-" * 45)
    for i, (tr, te) in enumerate(tscv.split(X), 1):
        Xtr, Xte = X.iloc[tr], X.iloc[te]
        ytr, yte = y.iloc[tr], y.iloc[te]
        model = resolve_classifier()                  # 可插拔:QUANTMILL_MODEL_CLF 换模型
        model.fit(Xtr, ytr)
        pred = (model.predict(Xte) > 0.5).astype(int)  # 分数→硬标签(默认 lgbm 与原 predict 等价)
        acc = accuracy_score(yte, pred)
        # 基准:永远猜训练集里的多数类 | baseline: always guess the majority class in the training set
        base = max(ytr.mean(), 1 - ytr.mean())
        accs.append(acc)
        base_accs.append(base)
        print(f"{i:>3} {len(tr):>8} {len(te):>8} {acc:>9.1%} {base:>7.1%}")

    mean_acc, mean_base = float(np.mean(accs)), float(np.mean(base_accs))
    edge = mean_acc - mean_base
    print("-" * 45)
    print(f"平均:模型 {mean_acc:.1%} vs 基准 {mean_base:.1%}  "
          f"优势 {edge:+.1%}  ->  " + ("有信号 ✅" if edge > 0.01 else "几乎没优势 ⚠️"))
    return {"mean_acc": mean_acc, "mean_base": mean_base, "edge": edge}


def walk_forward(X: pd.DataFrame, y: pd.Series, n_splits: int = config.N_SPLITS) -> pd.Series:
    """
    向前滚动生成【样本外】预测概率 P(涨),用于回测。
    Roll forward to generate [out-of-sample] predicted probabilities P(rise), used for backtesting.
    每一段测试集的预测,都只用它之前的数据训练 —— 和真实交易一样绝不偷看未来。
    Each test segment's prediction is trained only on data that precedes it — just like real trading, never peeking at the future.
    返回:一个概率序列(只覆盖能被预测的后半段,前面用于最初训练的部分是 NaN)。
    Returns: a probability series (covering only the predictable later portion; the earlier part used for initial training is NaN).
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)
    proba = pd.Series(index=X.index, dtype=float)  # 默认全 NaN | all NaN by default
    for tr, te in tscv.split(X):
        model = resolve_classifier()               # 可插拔:QUANTMILL_MODEL_CLF 换模型
        model.fit(X.iloc[tr], y.iloc[tr])
        proba.iloc[te] = model.predict(X.iloc[te])  # 分数=P(涨);默认 lgbm 与 predict_proba[:,1] 一致
    return proba


def train_full(X: pd.DataFrame, y: pd.Series) -> LGBMClassifier:
    """用全部数据训一个模型(用于看特征重要性、或给最新一天做实时预测)。
    Train one model on all the data (for inspecting feature importance, or making a live prediction for the latest day)."""
    model = _make_model()
    model.fit(X, y)
    return model


def feature_importance(model: LGBMClassifier) -> pd.Series:
    """哪些特征最有用(模型分裂时用得最多的)。
    Which features are most useful (the ones the model uses most when splitting)."""
    return pd.Series(model.feature_importances_, index=FEATURE_COLS).sort_values(
        ascending=False)


if __name__ == "__main__":
    from quantmill.data import get_ohlcv
    from quantmill.factor import build_dataset

    df = get_ohlcv("AAPL", "us", start="2018-01-01", end="2024-01-01")
    X, y, _ = build_dataset(df, horizon=5)
    print(f"数据集:{X.shape[0]} 行 × {X.shape[1]} 特征")

    res = time_series_cv(X, y, n_splits=5)

    model = train_full(X, y)
    print("\n最有用的 6 个特征:")
    print(feature_importance(model).head(6).round(1).to_string())
