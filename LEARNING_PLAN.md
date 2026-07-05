# AI 量化交易 · 学习手册与路线图

> 目标:自己实盘小资金交易赚钱 | 节奏:全天密集 ~10 天 | 起点:零基础(会 Python)
> 原则:**每天一个看得见的成果,边做边懂。前期全部用历史数据做实验,不碰真钱。**

---

## 项目结构

```
~/quant/
├── .venv/          # 隔离的 Python 虚拟环境(所有库装在这,不污染系统)
├── data/           # 存下载的历史数据
├── strategies/     # 策略代码
├── notebooks/      # Jupyter 实验
├── results/        # 回测结果、图表
└── LEARNING_PLAN.md  # 本文件
```

## 怎么运行(固定套路)

```bash
cd ~/quant
./.venv/bin/python strategies/01_first_backtest.py      # 跑某个脚本
./.venv/bin/pip install 包名                              # 装新库
```

> 小技巧:每次手动敲 `./.venv/bin/python` 很烦,可以先 `source .venv/bin/activate`
> 激活后直接用 `python`,完事 `deactivate` 退出。

---

## 核心认知(背下来)

整件事 = 四步循环:**数据 → 规则/模型 → 回测 → 实盘**,前三步永远在反复迭代。

衡量一个策略好坏,**永远不只看收益**,要一起看:
- **夏普比率(Sharpe)**:每承担一份风险换来多少收益。>1 不错,>2 很好。
- **最大回撤(Max Drawdown)**:从最高点跌到谷底亏多少。决定你能不能扛住、会不会割肉。
- **vs 买入持有**:跑不赢"啥也不干一直拿着" = 白忙活。

**头号杀手是"自欺欺人的回测"**:未来函数、过拟合、忽略手续费/滑点、用了拿不到的信息。
任何"历史上完美"的结果,先假设它是假的,去找哪里错了。

---

## 10 天计划(打勾追踪)

### 阶段一:地基
- [x] **Day 1 · 跑通第一条流水线** — 已完成 ✅
      `strategies/01_first_backtest.py`(SMA 均线交叉策略)
      学到:数据下载、策略类写法、回测、看懂核心指标、FractionalBacktest 坑
- [x] **Day 2 · 回测的陷阱** — 已完成 ✅
      `strategies/04_lookahead_cheat.py`(偷看明天 → 假赚 32632%)
      学到:未来函数怎么骗人、为什么真实 bug 藏得深、"结果越美越要怀疑"、样本外验证
- [x] **Day 3 · 风险管理与仓位** — 已完成 ✅
      `strategies/05_risk_management.py`(A满仓 / B加止损 / C半仓 三版本对比)
      学到:最大回撤是头号敌人、仓位控制最可靠(回撤砍半)、止损是双刃剑会被震荡扫、
      风控本身也必须用数据验证

### 阶段二:策略与 AI
- [x] **Day 4 · 经典策略原型** — 已完成 ✅
      `strategies/06_momentum_vs_meanreversion.py`(动量+21% vs 均值回归-6% vs 买入持有-10%)
      学到:动量追涨吃趋势/能躲暴跌怕震荡、均值回归高抛低吸吃震荡怕趋势(接飞刀)、
      二者性格相反、没有万能策略、要判断行情选武器
- [x] **Day 5 · 特征工程** — 已完成 ✅  `quantlib/features.py`
      18 个特征(收益率/均线偏离/RSI/波动率/量能/价格位置)+ make_label 打涨跌标注
      学到:模型是瞎子只吃数字、特征只能用"今天及以前"、只有标注能用未来(且最新几天要丢)
- [x] **Day 6 · 机器学习预测** — 已完成 ✅  `quantlib/model.py`
      LightGBM + 时序交叉验证(TimeSeriesSplit)+ walk-forward 样本外预测
      学到:绝不能打乱做CV(=未来函数)、别信样本内准确率、要跟"永远猜涨"的基准比、
      **准确率≠赚钱能力**(腾讯案例:模型准确率没优势,但择时避险把回撤 -73%→-55%)
- [ ] **Day 7 · 深度学习与 LLM 的边界** — 知道它们能干嘛、不能干嘛,别陷进去

> 🛠️ **已产出完整工具 `quantlib/`(2026-07-04)** — 端到端量化研究框架
> ```
> quantlib/data.py      统一多市场数据层(美股yfinance / A股·港股akshare,带双源回退+缓存)
> quantlib/features.py  特征工程 + 打标注
> quantlib/model.py     LightGBM 涨跌预测 + 时序CV + walk-forward
> quantlib/backtest.py  概率阈值策略接回 backtesting.py(含手续费滑点)
> quantlib/metrics.py   策略 vs 买入持有对比(含自算买入持有回撤)
> quantlib/report.py    生成 HTML 研究报告
> main.py               一键跑通:./.venv/bin/python main.py --symbol 00700 --market hk
> ```
> 已验证:美股AAPL🟡(回撤更小) / A股000001🔴(单边跌帮不上) / 港股00700✅(收益持平回撤大降)

### 阶段三:实盘
- [ ] **Day 8 · 模拟盘(paper trading)** — 交易所测试网,跑通"实时数据→信号→下单"闭环
- [ ] **Day 9 · 小资金实盘** — 用输得起的最小金额(几百块),暴露真实滑点/延迟/心理
- [ ] **Day 10 · 复盘与迭代框架** — 对比实盘 vs 回测差异,建立研究日志

---

## 铁律(贴在显示器上)
1. **先活下来,再谈赚钱。** 风控 > 策略。
2. **过拟合是头号杀手。** 历史完美 = 未来必死,先怀疑。
3. **回测必算成本**(手续费 + 滑点),否则结果是假的。
4. **样本外验证**:开发用一段数据,验证用另一段,绝不偷看。
5. **真实预期**:稳定盈利是马拉松。这 10 天是拿入场券,不是终点。

---

## 推荐资料(选读,别囤积)
- 书:Marcos López de Prado《Advances in Financial Machine Learning》— 量化 ML 圣经,挑前几章
- 库文档:`backtesting.py`、`ccxt`、`vectorbt`(进阶批量调参)、`lightgbm`
- 数据源:`ccxt`(加密,免费)、`yfinance`(美股)、`akshare`(A股)
