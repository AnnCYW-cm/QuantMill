# 🏭 quantmill · 开源全链条 AI 量化平台

[![CI](https://github.com/AnnCYW-cm/QuantMill/actions/workflows/ci.yml/badge.svg)](https://github.com/AnnCYW-cm/QuantMill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Tests](https://img.shields.io/badge/tests-95%20passing-brightgreen.svg)
![Coverage](https://img.shields.io/badge/coverage-42%25-yellow.svg)

**一个会自己拆穿自己的诚实量化平台**:从多市场数据 → 因子 → 模型 → 组合 → 执行,每一步都内建**抗过拟合的可信度检验**。它不给你看漂亮回测就让你上头,而是当面告诉你"这个策略到底成不成立"。

> An honest, full-chain open-source AI quant platform for **HK / US / A-share**.
> Data → factors → models → **cross-sectional selection** → backtest → **built-in credibility checks (DSR/PBO)** → cross-market validation → paper execution → web app.

---

## ⚠️ 诚实声明 / Honest disclaimer

这是**研究与学习框架,不是能直接实盘赚钱的产品**。经过本平台自己的可信度层反复拷问,当前结论是:

- **复杂 ML 排名模型是过拟合幻觉**:A股样本内年化 56%、超额 33%,但换到港股**亏 10%**,去掉前视偏差后**塌成 −7.7%**。
- **简单因子组合(价值+动量+低波)是"真但弱"的边际**:跨 A股/港股两个市场都为正、DSR 0.989,但档内超额只有 ~0.2–0.7%/期、胜率 52–55%,**能当研究基线,绝不可重仓**。

任何信号仅供研究,**别拿真钱跟**。详见 [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md)。

---

## 这个项目为什么存在(对标 Qlib)

对标微软 Qlib 的全链条完整度,补上它的三个空当:

1. **港/美/A 股一等公民** —— Qlib 港股要自己接;这里三市场同一套接口。
2. **可信度 / 抗过拟合内建主流程** —— DSR(去膨胀夏普)/ PBO(过拟合概率)/ 跨市场验证 / 前视偏差量化,全行业刻意回避的东西,这里是默认输出。
3. **上手友好 + 中英双语 + 网页台** —— 一条命令或双击启动,不是纯代码库。

---

## ✨ 能力总览 / Features

| 层 | 能力 |
|---|---|
| **数据** | 港/美/A 股,akshare + yfinance 双源回退 + 缓存;**美股 Alpaca 实时行情**(纯数据,不下单) |
| **因子** | 40+ 量价因子(表达式引擎)+ 基本面(PE/PB/市值)+ IC/RankIC 分析 |
| **横截面选股** | 全市场排名建模(非单股预测):`cross` 模块,面板 → 横截面 IC → 模型 → top-k 回测 |
| **两种策略** | **稳健因子组合**(固定配方零训练,跨市场验证过)vs **ML 排名**(LightGBM,对照反面教材) |
| **可信度 ★** | DSR / PBO(CSCV)/ 广度稳健性 / **跨市场验证** / **前视偏差量化** |
| **组合** | 等权 / TopK / 逆波动 / 最小方差(收缩协方差、波动率目标、A股制度) |
| **消息面** | LLM 情绪(Claude + 词典兜底,严格 point-in-time) |
| **执行** | 纸面账户 + Alpaca 美股适配器(纸面盘) |
| **界面** | Flask 网页台(7 页)+ 13 个 CLI 命令 + 双击启动 |

---

## 安装 / Install

```bash
cd ~/quant
brew install libomp                        # macOS 上 LightGBM 需要 OpenMP
./.venv/bin/pip install -e ".[dev]"        # 装完就有 quantmill 命令
# 可选依赖:.[llm] Claude情绪 · .[broker] Alpaca · .[web] 网页台
```

## 快速开始 / Quickstart

```bash
# —— 装上即试(离线,内置样本,秒出)——
quantmill cross backtest --sample   # 用随包小样本跑通选股回测,无需联网
quantmill experiment run examples/experiments/sample_demo.yaml  # 配置驱动的实验(离线)
quantmill niche cb --sample         # 可转债打新"诚实口径"(营销+13% → 实际~250元/年)

# —— 网页台(推荐)——
quantmill web                       # 起本地网页台,浏览器自动打开

# —— 横截面选股(真实全池,首次联网拉数据)——
quantmill cross ic --market cn      # 全市场横截面因子 IC 排行
quantmill cross backtest --market cn --model composite   # 稳健组合回测(默认)
quantmill cross validate            # 跨市场验证(A股 + 港股都为正才算稳健)
quantmill cross survivorship        # 量化前视/幸存者偏差有多毒

# —— 单股 / 组合 / 信号 ——
quantmill scan                      # 自选股「今日信号」面板
quantmill analyze AAPL us           # 深挖单只票
quantmill portfolio cn              # 组合回测 vs 等权基准
quantmill validate                  # 批量可信度体检(DSR/PBO)
```

自选股改 `watchlist.txt`(格式 `市场 代码`,如 `us AAPL`)。

## 启用美股实时行情(可选)

1. 在 [alpaca.markets](https://alpaca.markets) 免费注册,拿 **Paper Trading** 的 API Key ID + Secret。
2. 建 `~/quant/.alpaca`(已在 .gitignore):
   ```
   ALPACA_API_KEY_ID=xxx
   ALPACA_API_SECRET_KEY=yyy
   ```
3. 重启 `quantmill web` → 行情页从「🕒 延迟」变「🟢 实时 Alpaca」。仅美股;IEX 免费 feed;实时只在美股盘中有意义。

---

## 架构 / Architecture

```
quantmill/
├── config.py        中央配置 + 路径(单一来源)
├── data/            ① 多市场数据(双源回退+缓存)+ live.py 实时行情
├── factor/          ② 因子引擎(expr)+ 因子库(library)+ IC分析(analysis)
├── model/           ④ 模型(LightGBM)+ 时序CV/walk-forward
├── backtest/        ⑧ 单股回测(含成本滑点)
├── evaluation/      ⑬ 指标 vs 买入持有
├── credibility/  ★  ⑩ 可信度层:DSR/PBO(stats)+ 广度稳健(validate)
├── cross/        ★  横截面选股:universe/panel/ic/model/composite/backtest/run
├── portfolio/       ⑦ 组合优化(等权/topk/逆波动/最小方差)+ A股制度
├── llm/             ⑤ 消息面情绪(Claude + 词典兜底,PIT)
├── execution/       ⑨ 券商抽象(纸面 + Alpaca)+ 执行引擎
├── report/          ⑫ 单只报告 / 信号面板 / 工作台首页
├── web/             网页台(Flask 蓝图:market/cross_view/research/trading + static 前端)
├── workflow/        编排:pipeline + cli(13 命令)
└── watchlist.py     自选股加载
tests/               95 个离线测试(含「无未来函数」锁)
docs/                产品/架构/UML/研究纪要/行业调研
```

完整架构 + UML 图见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 核心铁律 / Iron rules

1. **无未来函数是地基,用测试焊死** —— 特征只用过去,只有 label 用未来;`cross` 的 walk-forward 有「砍未来数据不改过去打分」的锁死测试。
2. **诚实优先** —— 回测默认配 DSR/PBO,永远显示 vs 基准。
3. **过拟合是头号杀手** —— 历史完美 = 未来必死;记录"试了多少次 N"。
4. **跨市场验证** —— 一个市场赚是运气,两个独立市场都赚才可能是真的。
5. **偏差要量化,不能藏** —— 幸存者/前视偏差当面标出来、量出来。
6. **简单胜过复杂** —— 能跨市场活下来的简单因子,胜过看着漂亮的黑箱 ML。

---

## 文档索引 / Docs

| 文档 | 内容 |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 分层架构 + UML(组件/类/时序图,Mermaid) |
| [`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md) | 横截面调查全记录:ML幻觉 vs 稳健组合、跨市场、偏差 |
| [`docs/CLI.md`](docs/CLI.md) | 全部命令参考 |
| [`docs/PRODUCT_DESIGN.md`](docs/PRODUCT_DESIGN.md) | 产品设计蓝图(定位/架构/路线图) |
| [`docs/STATUS.md`](docs/STATUS.md) | 交付清单 / 当前状态 |
| [`docs/ai-quant-landscape.md`](docs/ai-quant-landscape.md) | 全球 AI 量化深度调研(22 家) |

## 开发 / Dev

```bash
./.venv/bin/python -m pytest -q        # 95 个离线测试
bash docs/build_pdf.sh                 # 生成带 UML 渲染的文档 PDF -> docs/quantmill-docs.pdf
```

## 许可 / License

研究与学习用途。非投资建议。数据源受各自条款约束。
Research & educational use. Not investment advice.
