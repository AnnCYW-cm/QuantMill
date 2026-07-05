# -*- coding: utf-8 -*-
"""
test_experiment.py —— 配置驱动实验(离线,用随包样本)
test_experiment.py —— config-driven experiment (offline, bundled sample)
"""

import os

from quantmill.workflow.experiment import DEFAULTS, load_config, run_experiment

_EX = os.path.join(os.path.dirname(__file__), "..", "examples", "experiments")


def test_load_config_fills_defaults_and_drops_unknown():
    cfg = load_config(os.path.join(_EX, "sample_demo.yaml"))
    assert cfg["sample"] is True
    assert cfg["model"] == "composite"
    assert set(cfg) == set(DEFAULTS)          # 未知键丢弃,缺省键补齐


def test_run_experiment_offline_sample():
    res = run_experiment({"name": "t", "sample": True, "model": "composite",
                          "k": 6, "horizon": 20})
    assert res["periods"] > 0
    assert {"年化", "超额年化", "夏普"} <= set(res["strat"])
    assert len(res["equity"]) > 0
    assert len(res["ic"]) > 0
    assert res["universe"] >= 10


def test_run_experiment_recipe_override():
    """改因子配方(不碰代码)也能跑,且配方被记录进结果。"""
    res = run_experiment({"name": "t2", "sample": True, "model": "composite",
                          "k": 6, "recipe": {"ey": 1, "vol_20d": -1}})
    assert res["config"]["recipe"] == {"ey": 1, "vol_20d": -1}
    assert res["periods"] > 0
