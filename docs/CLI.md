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
| `ic-decay` | **IC 衰减矩阵**:因子×未来h天横截面 IC,看信号多快衰减(定换仓频率)。需真实池(不支持 --sample) |
| `backtest` | 训练/组合打分 + top-k 回测 + DSR 可信度;指标含**夏普/Sortino/Calmar/信息比IR/换手率** |
| `validate` | **跨市场验证**:同一方法在 A股+港股各跑,看是否都为正 |
| `survivorship` | **量化前视/幸存者偏差**:全池 vs PIT(2023前已纳入)对比 |
| `neutralize` | **因子中性化**:各因子横截面 IC 原始 vs 对 size 中性化后(揪出"市值替身"因子) |
| `riskmodel` | **因子风险模型**:当前 top-k 组合的风险分解(因子波动 ⊕ 特质波动 + 各因子风险贡献) |
| `attribution` | **绩效归因**:把超额收益拆成 各因子主动暴露贡献 + 选股α(钱从哪来) |

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

## forward ★ —— 前瞻纸面记录(只前进,不回测)

投资经理的唯一硬要求:别再看回测,给我一条**不回看的前瞻曲线**。本命令把"风控后的稳健组合"接成每天跑一次的前瞻纸面账户:取最新数据 → 算目标持仓 → 按**当日真实收盘价**标记市值 → **只追加一个净值点**,到换仓日才换成新目标并按回撤开关调敞口。**历史净值点一旦写下就绝不改写**(由 8 个测试焊死)——这才是用真实流逝的时间兑现平台立身之本("回测会骗人")。

```
quantmill forward [run|status] [--market cn|hk|us] [--model composite|ml] \
                  [--cash 100000] [-k 20] [--horizon 20] [--dd-limit 0.12] [--refresh]
```

| action | 作用 |
|---|---|
| `run`(默认) | 联网取最新面板+现价,推进一步,追加今日净值点,存档 |
| `status` | 看当前前瞻曲线:起始日/净值点数/累计收益/最大回撤/当前持仓 |
| `auto` | **装每日自动推进**(macOS→launchd,其它→给 cron 一行),再也不用记得手点 |
| `unauto` | 卸载自动推进 |
| `loop` | 前台常驻自动推进(不想动系统调度时用,Ctrl+C 退出) |
| `tick` | 调度器内部调用:各市场推进一步即退出(一般不用手敲) |

- 状态存 `results/forward_<market>_<model>.json`。**每天/每周固定跑一次**,几个月后你就有一条真前瞻曲线——这条曲线能不能兑现回测里那点微弱 alpha,才是这平台唯一可信的证据。
- `--refresh` 强制拉最新数据(否则用缓存面板);首次拉全池较慢。
- ⚠️ 它**不能离线模拟**(前瞻的意义就是真实时间流逝);要在你自己机器上、随时间反复跑。同一天重复跑=更新今天,不新增点、不动历史。

**手动推进**
```bash
quantmill forward run --market cn                # 今天:建仓/推进一步(A股稳健组合)
quantmill forward run --market us --model ml     # 也可跟踪美股 ML 版做对照
quantmill forward status --market cn             # 看这条只前进的曲线长到哪了
```

**自动推进(装一次,天天自己跑)**
```bash
quantmill forward auto --markets cn,hk --at 16:40   # 每天 16:40 自动给 CN+HK 各推进一步(macOS)
quantmill forward unauto                            # 不想跑了就卸载
quantmill forward loop --markets cn --at 16:40      # 或前台常驻(留个终端/tmux 挂着)
```
- macOS 用 **launchd**:即使到点时机器在睡觉,**下次唤醒会补跑**;日志在 `results/forward_auto.log`。
- 因为按天幂等,**多跑几次无害**——重复跑只更新今天那个点,不会重复追加、不动历史。
- 非 macOS 会打印一行 cron,`crontab -e` 粘进去即可(工作日按时跑)。

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
起本地 Flask 网页台(8 页:总览/行情/组合/可信度/因子/选股/**前瞻曲线**/消息面/个股)。**前瞻曲线**页可视化 `forward` 的只前进净值线(推进一步/看曲线)。美股配 Alpaca 密钥可转实时行情。

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
