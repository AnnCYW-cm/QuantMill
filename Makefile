# Makefile —— 常用开发任务(make <目标>)| common dev tasks (make <target>)
# 统一入口是 `quantmill` 命令(装完即有);老的 quant.py/main.py 已移除。
PY  := ./.venv/bin/python
PIP := ./.venv/bin/pip
QM  := ./.venv/bin/quantmill

.PHONY: help install test lint scan validate cross web home docs-pdf clean

help:            ## 显示所有可用任务 | list tasks
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/  ->/'

install:         ## 可编辑安装(装完可用 quantmill 命令)| editable install
	$(PIP) install -e ".[dev]"

test:            ## 跑测试套件 | run the test suite
	$(PY) -m pytest -q

lint:            ## ruff 静态检查(需 pip install ruff)| lint
	$(PY) -m ruff check quantmill

scan:            ## 刷新自选股信号面板 | refresh signal panel
	$(QM) scan

validate:        ## 批量可信度验证 | batch credibility check
	$(QM) validate

cross:           ## 横截面跨市场验证(A股+港股)| cross-market validation
	$(QM) cross validate

web:             ## 启动网页台 | launch web dashboard
	$(QM) web

home:            ## 刷新主页 | rebuild home page
	$(QM) home

docs-pdf:        ## 生成文档 PDF(含 UML 渲染)| build docs PDF
	$(QM) docs-pdf --no-open

clean:           ## 清理构建缓存 | clean build artifacts
	rm -rf build dist *.egg-info quantmill/__pycache__ tests/__pycache__ .pytest_cache
