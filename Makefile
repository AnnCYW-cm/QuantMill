# Makefile —— 常用开发任务(make <目标>)| common dev tasks (make <target>)
# 注:命令用虚拟环境里的 python | uses the venv's python
PY := ./.venv/bin/python
PIP := ./.venv/bin/pip

.PHONY: help install test scan validate home clean

help:            ## 显示所有可用任务 | list tasks
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/  ->/'

install:         ## 安装为可编辑包(装完可用 quant 命令)| editable install
	$(PIP) install -e ".[dev]"

test:            ## 跑测试套件 | run the test suite
	$(PY) -m pytest tests/ -q

scan:            ## 刷新自选股信号面板 | refresh signal panel
	$(PY) quant.py scan

validate:        ## 批量可信度验证 | batch credibility check
	$(PY) quant.py validate

home:            ## 刷新主页 | rebuild home page
	$(PY) quant.py home

clean:           ## 清理构建缓存 | clean build artifacts
	rm -rf build dist *.egg-info quantmill/__pycache__ tests/__pycache__ .pytest_cache
