# 更新日志 / Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/);格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/)。

## [Unreleased]

### Added 新增
- **横截面选股(`cross` 模块)**:从"单股时序预测"升级到"全市场横截面排名选股"——universe / panel / ic / model / composite / backtest / run。
- **稳健因子组合**:固定配方零训练策略(价值+动量+低波),经跨市场验证(A股+港股都为正,DSR 0.989)。
- **跨市场验证** `cross validate` 与**前视/幸存者偏差量化** `cross survivorship`,作为可信度层的新关卡。
- **美股实时行情**:`data/live.py` 接 Alpaca(纯数据,不下单),有 key 用实时、无 key 退回 yfinance;网页显示实时/延迟标识。
- **网页台「🎯 选股」页**:模型切换(稳健组合 / ML)+ 跨市场验证条 + 诚实判决横幅。
- **文档**:重写 README;新增 `docs/ARCHITECTURE.md`(含 Mermaid UML)、`docs/RESEARCH_NOTES.md`(横截面调查全记录)、`docs/CLI.md`。
- **文档 PDF 一键生成**:`quantmill docs-pdf` / `docs/build_pdf.sh`(Mermaid 真渲成矢量图)。
- 开源基建:LICENSE(MIT)、CONTRIBUTING、CI(GitHub Actions)、issue/PR 模板、ruff/pre-commit 配置。

### Changed 变更
- `walk_forward_scores` 返回的 Series 恢复 `(date, symbol)` 索引名。
- 估值缓存逐列容错(缺列不再报错)。
- 网页全局异常处理返回真实 HTTP 状态码(保留 JSON 错误体)。

### 关键研究结论 / Key finding
经四道关(可信度 → 子区间 → 跨市场 → 前视偏差)拷问:**复杂 ML 排名模型是过拟合幻觉;简单价值/低波/动量因子组合是"真但弱"的边际,不可重仓。** 详见 `docs/RESEARCH_NOTES.md`。

## [0.1.0]
- 初始全链条平台:data / factor / model / backtest / credibility(DSR·PBO)/ portfolio / llm / execution / report / web / workflow;10 CLI 命令;中英双语;pip 可安装。
