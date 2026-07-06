# -*- coding: utf-8 -*-
"""可插拔 ModelProvider 测试 —— 离线,焊死契约/换模型/与原 LGBM 等价。"""
import numpy as np
import pandas as pd
import pytest

from quantmill.model.provider import (CLASSIFIERS, REGRESSORS,
                                      assert_model_contract, resolve_classifier,
                                      resolve_regressor)


def _xy(reg=False, n=80):
    rng = np.random.RandomState(1)
    X = pd.DataFrame({"a": rng.randn(n), "b": rng.randn(n), "c": rng.randn(n)})
    y = X["a"] - 0.5 * X["b"] + 0.1 * rng.randn(n)
    return X, (y if reg else (y > 0).astype(int))


def test_all_registered_pass_contract():
    for name in CLASSIFIERS.names():
        assert_model_contract(CLASSIFIERS.get(name))       # 分类器分数 ∈[0,1]
    for name in REGRESSORS.names():
        assert_model_contract(REGRESSORS.get(name))


def test_default_is_lgbm():
    assert resolve_classifier().name == "lgbm"
    assert resolve_regressor().name == "lgbm"


def test_env_swaps_model(monkeypatch):
    monkeypatch.setenv("QUANTMILL_MODEL_CLF", "logistic")
    monkeypatch.setenv("QUANTMILL_MODEL_RANKER", "ridge")
    assert resolve_classifier().name == "logistic" and resolve_classifier().task == "classifier"
    assert resolve_regressor().name == "ridge" and resolve_regressor().task == "regressor"


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        CLASSIFIERS.get("nope")


def test_lgbm_provider_equals_raw():
    """LGBMClassifierModel.predict 必须逐值等于原生 LGBMClassifier.predict_proba[:,1](零漂移)。"""
    from lightgbm import LGBMClassifier

    from quantmill.model.models import LGBMClassifierModel, make_lgbm_classifier
    X, y = _xy()
    prov = LGBMClassifierModel().fit(X, y)
    raw = make_lgbm_classifier(); raw.fit(X, y)
    assert isinstance(raw, LGBMClassifier)
    np.testing.assert_allclose(prov.predict(X), raw.predict_proba(X)[:, 1])


def test_pluggable_model_actually_trains_and_ranks():
    """换成 ridge 也能 fit+predict 出可排序的分数(证明真能插别的模型)。"""
    Xr, yr = _xy(reg=True)
    ridge = REGRESSORS.get("ridge").fit(Xr, yr)
    p = ridge.predict(Xr)
    assert len(p) == len(Xr) and np.isfinite(p).all()
    assert np.corrcoef(p, yr)[0, 1] > 0.5                   # 学到了正相关信号
