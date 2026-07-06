# quantmill 交付清单 / Status

> 截至 2026-07-06 · 15 层模块 · 137 测试全绿(+1 跳过)· 16 个 CLI 命令 · 网页台(8页,含前瞻曲线)· CI/docs 双绿 · 中英双语 · pip 可安装

---

## ✅ 已完成

### 一、全链条模块(data → 执行)
| 层 | 状态 | 要点 |
|---|---|---|
| **data ★** | ✅ | **可插拔 DataProvider**:四接口(bars/基本面/universe/quotes)+ Chain回退 + Caching + 注册表,一个环境变量换源;`live.py` **Alpaca 美股实时行情**(纯数据) |
| **factor** | ✅ | 表达式引擎 + 40+ 量价因子 + IC/RankIC 分析 |
| **model ★** | ✅ | **可插拔 ModelProvider**(fit/predict 契约,lgbm/logistic/ridge,环境变量换模型,可接自己的)+ 时序 CV/walk-forward |
| **backtest** | ✅ | 单股回测,含成本滑点 |
| **credibility ★** | ✅ | DSR(去膨胀夏普)+ PBO(CSCV)+ 广度稳健 |
| **cross ★** | ✅ | 横截面选股全链:universe/panel/ic/model/composite/backtest/run |
| **portfolio** | ✅ | 等权/topk/逆波动/最小方差 + 收缩协方差 + 波动率目标 + A股制度 |
| **llm** | ✅ | Claude 情绪 + 词典兜底,严格 PIT |
| **execution** | ✅ | 纸面账户 + Alpaca 适配器 |
| **paper ★** | ✅ | **前瞻纸面记录**:只前进不回看的净值曲线 + 每日自动推进(launchd/cron) |
| **report / web** | ✅ | 信号面板 + 工作台首页 + Flask 网页台(8页,含前瞻曲线) |
| **workflow** | ✅ | pipeline + cli(16 命令) |

### 二、横截面选股(2026-07 主线)
- ✅ 全 CSI300(300只)+ 港股蓝筹(86只)面板,横截面 IC。
- ✅ 两种策略:**稳健因子组合**(固定配方零训练,跨市场验证过,DSR 0.989)+ **ML 排名**(对照)。
- ✅ **跨市场验证**(`cross validate`):A股+港股都为正才算稳健。
- ✅ **前视/幸存者偏差量化**(`cross survivorship`):PIT 池对比。
- ✅ 网页「🎯 选股」页:模型切换 + 跨市场验证条 + 诚实判决横幅。

### 三、实时数据
- ✅ Alpaca 美股实时行情接入(`data/live.py`),有 key 用实时、无 key 退回 yfinance。
- ✅ 密钥支持环境变量或 `~/quant/.alpaca` 文件(双击启动也读);行情页显示 🟢实时/🕒延迟。

### 三·补(2026-07-06 会话:往"合格底座"推的三步)
- ✅ **前瞻实证**(`paper/`):把风控后组合接成**只前进、不回看**的前瞻纸面曲线——
  每次按当日真实收盘价追加一个净值点,**历史绝不改写**(8 测试焊死);网页「📜前瞻曲线」页
  可视化;`forward auto` 每日自动推进(macOS launchd,睡眠错过下次唤醒补跑;非 mac 给 cron)。
  已在本机按 A股收盘 15:10 装上、首个净值点已建仓。
- ✅ **可插拔 DataProvider**(`data/`):把数据源从焊死改为可插拔(四小接口 + 组合器 + 注册表),
  换成自己的付费/机构数据只改一个环境变量、零改 15 处调用点;契约测试拒未来 `available_date`/
  前视 universe(见 `docs/DATAPROVIDER.md`)。
- ✅ **严格 PIT**:`build_panel` 估值对齐升级为 `merge_asof(available_date)`——接带真实披露滞后的
  财报源不泄露未来(3 测试焊死),老缓存自动退化等价原行为。
- ✅ **CI 自动化 + 修绿 docs**:`ci.yml`(matrix os×py 测试)长绿;`Deploy docs` 从一直红修成绿
  (改用 `mkdocs gh-deploy`,不依赖 Pages 设置)。

### 四、工程质量
- **137 个离线测试全绿**(+1 跳过;合成数据、确定性、可复现);**CI matrix(ubuntu/macos × py3.9/3.12)双绿**。
- **核心锁死**:「无未来函数」(特征/组合/情绪/cross walk-forward)+「只前进不回看」(前瞻记录)+「严格 PIT」(available_date 不早于数据日)+ DataProvider 契约。
- 中英双语 · pip 可安装(`[dev][llm][broker][web][parquet]`)· GitHub 就绪(CI/Pages/PyPI 工作流)。

### 五、文档
- `README.md` — 项目门面(已更新)
- `docs/ARCHITECTURE.md` — 架构 + UML(Mermaid 组件/类/时序/数据流)
- `docs/RESEARCH_NOTES.md` — 横截面调查全记录(ML幻觉 vs 稳健组合、跨市场、偏差)
- `docs/CLI.md` — 全命令参考
- `docs/DATAPROVIDER.md` — 可插拔数据层设计 + 接入你自己的数据
- `docs/PRODUCT_DESIGN.md` — 产品设计蓝图
- `docs/ai-quant-landscape.md` — 全球 AI 量化调研(22家)

---

## ⬜ 还没做

### 接真实世界(有账号/密钥就能做)
| 项 | 卡在哪 |
|---|---|
| Claude 真情绪 | 缺 `ANTHROPIC_API_KEY` |
| Alpaca 真纸面盘下单 | 缺密钥(实时行情已通,下单未启用——用户暂不做下单) |
| A股/港股实时行情 | Alpaca 仅美股;A股实时需券商/付费源 |
| 历史新闻数据 | 免费源无 → 情绪因子暂不能回测 alpha |

### 研究深化
| 项 | 说明 |
|---|---|
| **修全幸存者偏差** | PIT 只修了"前视纳入"一半;"后被踢出"的股需付费成分史。**数据层已可插拔**,接了付费源就能补(hk/us 亦然) |
| 真实前瞻曲线 | `forward` 已挂上每日自动推进,但真正可信要**积累几个月**前瞻净值——时间问题,非代码 |
| 拉长历史 | 估值仅近三年;量价可往前推到 2018,多几个 regime 把结论钉死 |
| ROE/成长因子 | 现只接了估值(ey/bp/size),质量/成长基本面待接 |

---

## 最诚实的一条

> **平台本身很成熟,但装在里面的策略只有"真但弱"的边际。** 经过四道关(可信度→子区间→跨市场→偏差)的拷问:复杂 ML 是过拟合幻觉,简单价值/低波/动量因子是真但弱、不可重仓。这也正是平台最值钱的地方 —— 它会当面拆穿漂亮回测,而不是拿它骗你。详见 `docs/RESEARCH_NOTES.md`。

---

## 附:16 命令速查
`scan · validate · analyze · factors · portfolio · news · paper · cross · risk · experiment · niche · textfactor · forward · web · home · docs-pdf`
（详见 `docs/CLI.md`）
