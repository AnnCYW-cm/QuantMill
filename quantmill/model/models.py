# -*- coding: utf-8 -*-
"""
models.py —— 具体模型实现(可插拔 ModelProvider 的实现层)
=====================================================================
统一契约:fit(X,y) -> self;predict(X) -> 实数分数(越大越看多)。
  · 分类器(单股 P涨):predict = predict_proba[:,1]
  · 回归器(横截面打分):predict = 预测收益
参数与原写死的 LGBM 逐字一致,默认换源不改任何回测结果。
sklearn 的 logistic/ridge 作第二实现,证明可插拔(无新依赖,sklearn 本就是依赖)。
"""
from __future__ import annotations


def make_lgbm_classifier():
    """单股分类器工厂(原 model._make_model 的参数,浅树+强正则防过拟合)。"""
    from lightgbm import LGBMClassifier
    return LGBMClassifier(
        n_estimators=300, learning_rate=0.03, max_depth=4, num_leaves=15,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
        random_state=42, n_jobs=-1, verbose=-1)


def make_lgbm_regressor():
    """横截面回归器工厂(原 cross.walk_forward_scores 参数,deterministic 可复现)。"""
    from lightgbm import LGBMRegressor
    return LGBMRegressor(
        n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=80,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0,
        random_state=0, n_jobs=-1, verbose=-1, deterministic=True, force_row_wise=True)


# ------------------------------------------------------------ LightGBM --------
class LGBMClassifierModel:
    name = "lgbm"
    task = "classifier"

    def fit(self, X, y):
        self._m = make_lgbm_classifier()
        self._m.fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict_proba(X)[:, 1]      # P(涨)


class LGBMRegressorModel:
    name = "lgbm"
    task = "regressor"

    def fit(self, X, y):
        self._m = make_lgbm_regressor()
        self._m.fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict(X)


# ------------------------------------------------ sklearn 线性(第二实现)------
class LogisticModel:
    name = "logistic"
    task = "classifier"

    def fit(self, X, y):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        self._m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        self._m.fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict_proba(X)[:, 1]


class RidgeModel:
    name = "ridge"
    task = "regressor"

    def fit(self, X, y):
        from sklearn.linear_model import Ridge
        self._m = Ridge(alpha=1.0)
        self._m.fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict(X)
