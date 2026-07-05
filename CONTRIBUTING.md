# 贡献指南 / Contributing

欢迎参与 quantmill!这是一个**诚实优先**的开源量化平台 —— 贡献时请守住它的立身之本。

## 铁律(PR 会按这些审)/ Iron rules

1. **无未来函数**:特征只能用过去,只有 label 用未来。任何触碰因子/面板/回测的改动,必须保证不偷看未来,并由测试覆盖。
2. **诚实优先**:不夸大回测。新增策略必须带可信度评估(DSR/PBO 或跨市场验证),并显示 vs 基准。
3. **偏差要标注**:幸存者/前视/数据偏差要在代码注释和输出里当面说明,不藏。
4. **看比例不看单只**:一只跑赢是运气,广度稳健才算数。

## 开发环境 / Dev setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # 核心 + pytest
brew install libomp              # macOS 上 LightGBM 需要
pytest -q                        # 应全绿
```

可选依赖:`.[llm]`(Claude 情绪)、`.[broker]`(Alpaca)、`.[web]`(网页台)。

## 提交前自查 / Before you PR

- [ ] `pytest -q` 全绿(CI 也会跑)。
- [ ] 新功能带测试;**离线、合成数据、确定性**(不依赖实时网络,见 `tests/conftest.py`)。
- [ ] 碰了因子/面板/模型 → 有"无未来函数"层面的测试或论证。
- [ ] 中英双语注释(与现有风格一致)。
- [ ] 没有硬编码密钥;密钥走环境变量或 `.alpaca` 文件。
- [ ] 若改了文档,`quantmill docs-pdf` 能正常生成。

## 代码风格 / Style

- 已配置 `ruff`(见 pyproject `[tool.ruff]`):`ruff check quantmill`。
- 可选 `pre-commit install` 自动跑格式检查。
- 保持模块单向依赖、配置走 `config.py` 单一来源。

## 加新东西该放哪 / Where things go

| 类型 | 位置 |
|---|---|
| 新因子 | `factor/library.py`(一行表达式) |
| 新横截面策略 | `cross/composite.py` 或新打分函数 |
| 新可信度检验 | `credibility/` |
| 新数据源 | `data/`(带容错回退) |
| 新命令 | `workflow/cli.py` |

架构详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 报告问题 / Issues

用 issue 模板,附:命令、市场、报错、环境(OS/Python 版本)。数据源类问题请注明是否 `ProxyError`(akshare eastmoney 在部分网络下不通,会自动回退 yfinance)。

---
提交即视为同意以 MIT 许可贡献你的代码。
