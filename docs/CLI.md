# CLI 命令参考 / Command Reference

装完 `pip install -e .` 后,`quantmill` 即为命令入口。通用参数:`--start`(默认 2018-01-01)、`--end`、`--horizon`(默认 5,cross 默认 20)。

```
quantmill <命令> [参数]
```

---

## cross ★ —— 横截面选股(今天的主线)

全市场排名建模。`action` 四选一,`--model` 选策略。

```
quantmill cross <action> [--model composite|ml] [--market cn|hk|us] [--quick] [-k N] [--cost 0.0015] [--long-short] [--horizon 20]
```

| action | 作用 |
|---|---|
| `ic` | 横截面因子 RankIC 排行(哪些因子在选股上有信息) |
| `backtest` | 训练/组合打分 + top-k 回测 + DSR 可信度 |
| `validate` | **跨市场验证**:同一方法在 A股+港股各跑,看是否都为正 |
| `survivorship` | **量化前视/幸存者偏差**:全池 vs PIT(2023前已纳入)对比 |

| --model | 说明 |
|---|---|
| `composite`(默认) | 稳健因子组合(ey+bp+动量+低波,固定配方零训练,跨市场验证过) |
| `ml` | 43 因子 LightGBM 排名(A股漂亮但港股翻车,当反面对照) |

**示例**
```bash
quantmill cross ic --market cn
quantmill cross backtest --market hk --model composite -k 15
quantmill cross validate --model composite
quantmill cross survivorship --model ml         # 看 ML 去偏差后崩成负
```
> 首次会拉全池数据(~15分钟)并缓存到 `data/panel_<market>.pkl`;之后秒开。`--quick` 用 10 只快速试。

---

## risk ★ —— 风控/仓位层(等权满仓 vs 风控后)

投资经理视角:alpha 弱时决定生死的是仓位和回撤。这一层给选股回测套上真实资金管理:**逆波动加权 + 单只封顶 + 波动率目标(控总敞口)+ 回撤开关(跌多了自动降仓)**,并与"等权满仓"对照。

```
quantmill risk [--market cn] [--sample] [--model composite|ml] [-k 20] \
               [--target-vol 0.15] [--max-weight 0.15] [--dd-limit 0.12]
```

典型效果(真实 A股 ML 模型):波动 26%→18%、最大回撤 −12.6%→−7.4%、收益让渡但**夏普反而略升**。全部严格因果(波动/回撤只取到上一期)。

---

## experiment ★ —— 配置驱动的实验(YAML)

用一个 YAML 定义实验(市场/因子配方/模型/参数/日期),可复现地跑,结果自动存档到 `results/experiments/<时间戳>_<名字>/`。**换因子/参数不用改代码。**

```
quantmill experiment run <config.yaml> [--no-save]
quantmill experiment list
```

**示例**
```bash
quantmill experiment run examples/experiments/sample_demo.yaml   # 离线样本,秒出
quantmill experiment run examples/experiments/cn_composite.yaml  # A股稳健组合
quantmill experiment list
```

YAML 可配项:`name / market(cn/hk/us) / model(composite/ml) / horizon / k / cost / start / sample / recipe(因子配方) / init_train / step`。改 `recipe` 就能换因子组合:
```yaml
name: my-value-tilt
market: cn
model: composite
recipe: { ey: 1, bp: 1, vol_20d: -1 }   # 正=越大越好,负=越小越好
```
存档内容:`config.yaml`(可复现)+ `result.json`(指标/DSR/IC)+ `equity.csv` + `ic.csv`。

---

## textfactor ★ —— LLM 文本 → 结构化因子

比标量情绪深一层:让 LLM 从新闻/公告**分类抽取**三维结构化信号(展望 / 指引 / 风险),组合成因子,再严格 PIT 聚合成横截面因子,接进可信度框架。

```
quantmill textfactor [SYMBOL MARKET] [--demo] [--limit 10]
```
- `--demo`:内置示例标题,离线看抽取效果。
- 带 `SYMBOL MARKET`:抓真实新闻做抽取(你机器上跑)。
- ⚠️ 只抽取"文本说了什么"(分类),**不预测涨跌**(防 LLM 用记忆的未来作弊);免费源无历史新闻 → alpha 暂不能回测,须过可信度层。

### 可插拔 LLM 后端(不锁死贵的 Claude)

LLM 路径走 **OpenAI 兼容**接口,配 3 个环境变量即可换任意便宜/免费/本地方案,不改代码;不配则**词典兜底**(离线)。

```bash
# DeepSeek(便宜、中文强)
export QUANTMILL_LLM_BASE_URL=https://api.deepseek.com/v1
export QUANTMILL_LLM_MODEL=deepseek-chat
export QUANTMILL_LLM_KEY=sk-...

# 通义千问 qwen-turbo(全场最便宜、中文最准、送免费额度)
export QUANTMILL_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export QUANTMILL_LLM_MODEL=qwen-turbo

# 本地 Ollama(零成本、隐私,先 `ollama run qwen3:4b`)
export QUANTMILL_LLM_BASE_URL=http://localhost:11434/v1
export QUANTMILL_LLM_MODEL=qwen3:4b
export QUANTMILL_LLM_KEY=ollama
```
也兼容 `OPENAI_BASE_URL`/`OPENAI_API_KEY`;或退回 `ANTHROPIC_API_KEY` 走 Claude。CLI 会显示当前后端(如 `后端 api.deepseek.com(deepseek-chat)`)。

代码里 `cross_text_factor(news_by_symbol, panel_index)` 直接产出 (date, symbol) 因子,可喂 `cross` 的横截面 IC / 可信度检验。

---

## niche ★ —— 散户结构性机会验证(诚实口径)

深度调研结论:免费横截面因子 alpha 真实但极弱;散户唯一有证据的真实机会在 A股结构性红利。本命令用平台的"诚实"框架验证它们**到底还有多少肉**——把营销口径("首日均涨20%!")翻译成诚实口径(扣中签率/成本后的每账户期望)。

```
quantmill niche cb [--sample] [--win-rate 0.00003]   # 可转债打新:破发率+首日分布+每账户期望
quantmill niche etf [--cost 0.002]                   # ETF折溢价:当前够套利的只数
```

- `cb --sample`:用随包合成样本**离线秒出**;不带 `--sample` 则联网拉真实数据(需你自己机器,本环境 eastmoney 常不通)。
- ⚠️ 可转债期望**对中签率极敏感**,`--win-rate` 填你账户的真实值;首日翻卖≠持有到期(信用违约是独立尾部风险)。
- ETF 是**当前横截面监控**(此刻有几只折溢价超成本),不是回测。

---

## scan —— 自选股「今日信号」面板

```
quantmill scan [--quick]
```
对 `watchlist.txt` 里的票逐只出模型信号(P(涨)+ 持有/空仓建议),刷新工作台首页。

## validate —— 批量可信度体检

```
quantmill validate [--quick]
```
对一篮子票跑 DSR/PBO/广度,回答"这套策略是不是靠运气/过拟合"。

## analyze —— 深挖单只票

```
quantmill analyze <symbol> <market> [--no-cv]
```
单票完整报告:特征 → 时序 CV → walk-forward 样本外 → 回测 vs 买入持有。`--no-cv` 跳过交叉验证更快。
例:`quantmill analyze AAPL us` / `quantmill analyze 00700 hk`

## factors —— 因子有效性排行(单股时序 IC)

```
quantmill factors <symbol> <market>
```
单票上每个因子的 IC/RankIC 排行。⚠️ 单股高 IC ≠ 能赚钱,需过可信度层。

## portfolio —— 组合回测

```
quantmill portfolio <market> [--method topk|invvol|minvar|equal] [--k N] [--vol-target 0.15] [--quick]
```
组合配置 + 回测 vs 等权基准。含收缩协方差、波动率目标、A股制度(涨跌停/印花税/T+1)。

## news —— 消息面情绪(LLM)

```
quantmill news <symbol> <market> [--limit 12]
```
LLM(Claude Haiku)给近期新闻打情绪分;无 `ANTHROPIC_API_KEY` 走词典兜底。⚠️ 情绪≠涨跌,免费源无历史新闻→暂不能回测其 alpha。

## paper —— 纸面交易闭环

```
quantmill paper <run|status|reset> [market] [--method] [--k] [--cash] [--quick] [--broker paper|alpaca] [--horizon]
```
- `run`:按组合方法生成目标持仓并下单(纸面/或 Alpaca 纸面盘)。
- `status`:看纸面账户。`reset`:重置初始资金。
- `--broker alpaca` 需 `pip install -e ".[broker]"` + `ALPACA_API_KEY_ID/SECRET`。

## web —— 网页台

```
quantmill web [--port 8787] [--no-open]
```
起本地 Flask 网页台(7 页:总览/行情/组合/可信度/因子/选股/个股/消息面)。美股配 Alpaca 密钥可转实时行情。

## home —— 刷新工作台首页

```
quantmill home
```
重建 `results/index.html`。

## docs-pdf —— 生成文档 PDF(含 UML 渲染)

```
quantmill docs-pdf [--no-open]
```
把 README + 架构&UML + 研究纪要 + CLI + 交付清单渲成一本 `docs/quantmill-docs.pdf`(Mermaid 图真渲成矢量图)。等价于 `bash docs/build_pdf.sh`。首次会装 puppeteer(下 Chromium 约150MB,仅一次),之后秒级。

---

## 环境变量 / 密钥

| 变量 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude 情绪(`news`);无则词典兜底 |
| `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` | Alpaca 券商 + 美股实时行情;也可写进 `~/quant/.alpaca` 文件(双击启动也读) |

## 数据文件 / 缓存

| 路径 | 内容 |
|---|---|
| `watchlist.txt` | 自选股(`市场 代码`,如 `us AAPL`) |
| `data/` | OHLCV / 估值 / 面板缓存(`panel_<market>.pkl`) |
| `results/` | 报告 / 图表 / 工作台首页 |
| `paper_account.json` | 纸面账户状态 |
| `.alpaca` | Alpaca 密钥(不入库) |
