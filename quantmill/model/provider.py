# -*- coding: utf-8 -*-
"""
provider.py —— 可插拔 ModelProvider(照 data.provider 同构)
=====================================================================
契约:fit(X,y)->self;predict(X)->实数分数(越大越看多)。按任务分两个注册表:
  CLASSIFIERS(单股 P涨)/ REGRESSORS(横截面打分)。
换模型:环境变量 QUANTMILL_MODEL_CLF / QUANTMILL_MODEL_RANKER=名字(如 logistic/ridge),
或代码里 register() 自己的实现——就像换数据源一样,不改调用点。
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from quantmill.model.models import (LGBMClassifierModel, LGBMRegressorModel,
                                    LogisticModel, RidgeModel)


@runtime_checkable
class ModelProvider(Protocol):
    name: str
    task: str                       # "classifier" | "regressor"
    def fit(self, X, y): ...        # 训练;返回自身
    def predict(self, X): ...       # 实数分数:clf->P(涨)∈[0,1],reg->预测收益


class _ModelRegistry:
    def __init__(self, task: str):
        self.task = task
        self._m: dict = {}

    def register(self, provider_cls):
        self._m[provider_cls.name] = provider_cls

    def get(self, name: str):
        if name not in self._m:
            raise ValueError(f"{self.task} 没有模型 '{name}';已注册:{list(self._m)}")
        return self._m[name]()          # 每次取一个新实例(可反复 fit)

    def names(self):
        return list(self._m)


CLASSIFIERS = _ModelRegistry("classifier")
REGRESSORS = _ModelRegistry("regressor")
CLASSIFIERS.register(LGBMClassifierModel)
CLASSIFIERS.register(LogisticModel)
REGRESSORS.register(LGBMRegressorModel)
REGRESSORS.register(RidgeModel)


def resolve_classifier():
    """单股分类器:QUANTMILL_MODEL_CLF 覆盖,默认 lgbm。"""
    return CLASSIFIERS.get(os.environ.get("QUANTMILL_MODEL_CLF", "lgbm"))


def resolve_regressor():
    """横截面打分器:QUANTMILL_MODEL_RANKER 覆盖,默认 lgbm。"""
    return REGRESSORS.get(os.environ.get("QUANTMILL_MODEL_RANKER", "lgbm"))


def assert_model_contract(provider):
    """契约:fit 后 predict 返回等长有限分数;分类器分数须在 [0,1]。"""
    n = 60
    rng = np.random.RandomState(0)
    X = pd.DataFrame({"a": rng.randn(n), "b": rng.randn(n)})
    y = (X["a"] + 0.1 * rng.randn(n) > 0)
    if provider.task == "regressor":
        y = y.astype(float)
    provider.fit(X, y)
    p = np.asarray(provider.predict(X), dtype=float)
    assert len(p) == n, "predict 长度须等于样本数"
    assert np.isfinite(p).all(), "predict 不得有 NaN/Inf"
    if provider.task == "classifier":
        assert ((p >= 0) & (p <= 1)).all(), "分类器分数须为概率 [0,1]"
    return p
