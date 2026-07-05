# quantmill 架构与 UML / Architecture & UML

> 本文用 [Mermaid](https://mermaid.js.org) 画图,GitHub 与多数 Markdown 预览器可直接渲染。
> 覆盖:分层架构、模块依赖(组件图)、关键类图、核心流程时序图、数据流。

---

## 1. 分层架构总览 / Layered overview

quantmill 是一条**从数据到执行的全链条**,横切一层**可信度(credibility)**贯穿始终。

```mermaid
flowchart TD
    subgraph SRC[数据源 External]
        AK[akshare 港/A股]
        YF[yfinance 美/港股]
        ALP[Alpaca 美股实时/纸面]
        NEWS[新闻/情绪源]
    end

    DATA[data<br/>多市场OHLCV·双源回退·缓存<br/>live.py 实时行情]
    FACTOR[factor<br/>表达式引擎·40+因子·IC分析]
    MODEL[model<br/>LightGBM·时序CV/walk-forward]
    CROSS[cross ★<br/>横截面选股:面板·IC·模型·组合·回测]
    BT[backtest<br/>单股回测·成本滑点]
    PORT[portfolio<br/>等权/topk/逆波动/最小方差]
    LLM[llm<br/>Claude情绪·词典兜底·PIT]
    CRED[credibility ★<br/>DSR·PBO·广度·跨市场·偏差量化]
    EXEC[execution<br/>Broker抽象·纸面/Alpaca]
    REPORT[report / web<br/>信号面板·工作台·网页台]
    CLI[workflow<br/>pipeline + cli 10命令]

    SRC --> DATA --> FACTOR
    FACTOR --> MODEL --> BT
    FACTOR --> CROSS
    DATA --> CROSS
    CROSS --> CRED
    BT --> CRED
    MODEL --> PORT --> EXEC
    NEWS --> LLM --> FACTOR
    CRED -.贯穿校验.-> REPORT
    CROSS --> REPORT
    PORT --> REPORT
    CLI --> DATA & FACTOR & CROSS & PORT & EXEC & REPORT
    ALP --> DATA
```

**读法**:实线=数据/控制流;`credibility` 是横切关注点(贯穿校验),不是链条末端的一站。

---

## 2. 模块依赖 / Package (component) diagram

```mermaid
flowchart LR
    config[config.py 中央配置/路径]
    watchlist[watchlist.py]

    data --> config
    factor --> data
    model --> factor
    backtest --> model & factor
    credibility --> factor & model & backtest
    cross --> data & factor & model & credibility
    portfolio --> model & factor
    llm --> config
    execution --> portfolio & model
    report --> data & factor & model & credibility & portfolio
    web --> data & cross & credibility & portfolio & execution & report
    workflow --> report & cross & portfolio & execution & llm
    data --> watchlist

    classDef moat fill:#1f6f43,stroke:#2ecc71,color:#fff;
    class credibility,cross moat;
```

> 依赖单向向下,`config` 是所有模块的单一配置来源。护城河模块(绿色)= `credibility` + `cross`。

---

## 3. 关键类图 / Class diagrams

### 3.1 券商抽象(执行层)

```mermaid
classDiagram
    class Broker {
        <<abstract>>
        +cash: float
        +positions() dict
        +submit(orders) list
        +net_liq(prices) float
    }
    class PaperBroker {
        -state_path: str
        +submit(orders)
        +reset(init_cash)
    }
    class AlpacaBroker {
        -_client: TradingClient
        -_real: bool
        +submit(orders)
    }
    Broker <|-- PaperBroker
    Broker <|-- AlpacaBroker
    note for AlpacaBroker "需 ALPACA_API_KEY_ID / SECRET\n默认纸面端点;可注入 mock client 做离线测试"
```

### 3.2 情绪打分器(LLM 层)

```mermaid
classDiagram
    class Scorer {
        <<interface>>
        +score(texts) list~float~
    }
    class LexiconScorer {
        +score(texts) list
        note_词典兜底_无需API
    }
    class AnthropicScorer {
        -model_claude_haiku
        +score(texts) list
    }
    Scorer <|.. LexiconScorer
    Scorer <|.. AnthropicScorer
    note for AnthropicScorer "无 ANTHROPIC_API_KEY 时\n自动退回 LexiconScorer"
```

### 3.3 横截面模块(cross)函数式管线

`cross` 以函数管线为主(非重类),核心数据结构是 **MultiIndex(date, symbol) 面板**:

```mermaid
classDiagram
    class Panel {
        <<Panel>>
        +index_date_symbol
        +量价因子列_40plus
        +基本面_ey_bp_size
        +fwd_未来收益标签
    }
    class universe {
        +csi300() list
        +csi300_pit(asof) PIT池
        +universe(market) list
    }
    class panel_mod {
        +build_panel(symbols, market) Panel
        +factor_columns(panel) list
    }
    class ic {
        +daily_ic(panel, factor)
        +ic_table(panel, factors)
    }
    class model {
        +rank_normalize(panel, cols)
        +walk_forward_scores(panel) Series
    }
    class composite {
        +ROBUST_RECIPE dict
        +composite_score(panel) Series
    }
    class backtest {
        +topk_backtest(panel, score) dict
    }
    class run {
        +get_panel(market) Panel
        +run_ic(market)
        +run_backtest(market, model)
        +run_validate(model) 跨市场
        +run_survivorship(model) 偏差量化
    }
    universe --> panel_mod
    panel_mod --> Panel
    Panel --> ic
    Panel --> model
    Panel --> composite
    model --> backtest
    composite --> backtest
    run --> panel_mod
    run --> model
    run --> composite
    run --> backtest
```

---

## 4. 核心流程时序图 / Sequence diagrams

### 4.1 `quantmill cross backtest`(横截面选股回测)

```mermaid
sequenceDiagram
    actor U as 用户
    participant CLI as workflow.cli
    participant Run as cross.run
    participant Panel as cross.panel
    participant Data as data.get_ohlcv
    participant Score as composite / walk_forward
    participant BT as cross.backtest
    participant Cred as credibility.stats

    U->>CLI: quantmill cross backtest --model composite
    CLI->>Run: run_backtest(market, model)
    Run->>Panel: get_panel(market) 有缓存直接读 panel_market.pkl
    alt 无缓存
        Panel->>Data: get_ohlcv(每只票) + 估值
        Data-->>Panel: OHLCV + PE/PB/市值
        Panel-->>Run: MultiIndex(date,symbol) 面板 + 落盘缓存
    end
    Run->>Score: 打分(composite=固定配方 / ml=purged walk-forward)
    Score-->>Run: score(date,symbol)
    Run->>BT: topk_backtest(panel, score, k)
    BT-->>Run: 策略 vs 等权基准 曲线+指标
    Run->>Cred: deflated_sharpe_ratio(收益, k变体做多重检验)
    Cred-->>Run: DSR
    Run-->>U: 指标表 + DSR + 诚实警告
```

### 4.2 网页实时行情(Alpaca 优先,yfinance 兜底)

```mermaid
sequenceDiagram
    participant FE as 前端 loadQuotes
    participant API as /api/quotes
    participant Q as _get_quotes
    participant YF as yfinance
    participant Live as data.live (Alpaca)

    FE->>API: GET /api/quotes?market=us
    API->>Q: _get_quotes(syms, "us")
    Q->>YF: 下载日线(历史spark + 昨收)
    YF-->>Q: 收盘序列
    alt market==us 且有 .alpaca 密钥
        Q->>Live: alpaca_last_prices(syms)
        Live-->>Q: 实时成交价 → 覆盖 price/chg, source=alpaca
    else 无密钥/失败
        Q-->>Q: 沿用 yfinance 延迟价, source=yfinance
    end
    Q-->>API: quotes + source
    API-->>FE: JSON
    FE->>FE: 顶部标识 🟢实时 / 🕒延迟
```

### 4.3 网页横截面页(后台计算 + 轮询)

```mermaid
sequenceDiagram
    participant FE as 前端 loadCross
    participant API as /api/cross
    participant TH as 后台线程 _compute_cross_bg
    participant Cross as cross.run

    FE->>API: GET /api/cross?market=cn&model=composite
    API->>TH: 启动线程(若未在跑)
    API-->>FE: {status: computing}
    loop 每2秒轮询
        FE->>API: GET /api/cross ...
        alt 计算中
            API-->>FE: {status: computing, stage}
        else 完成
            API-->>FE: {status: ready, data}
        end
    end
    TH->>Cross: 面板→打分→回测→DSR→跨市场验证
    Cross-->>TH: 指标+曲线+IC+valid[]
    TH->>TH: 写入 _XCACHE[market:model]
```

---

## 5. 横截面数据流 / Cross-sectional data flow

从"每股单练"到"全市场选股"的范式,数据形态的转变:

```mermaid
flowchart LR
    A["每只票<br/>时间序列表<br/>OHLCV+因子"] -->|堆叠 stack| B["面板 Panel<br/>MultiIndex(date, symbol)<br/>每行=某天某股的因子+未来收益"]
    B -->|每日横截面| C["横截面 IC<br/>同一天全市场<br/>因子 vs 未来收益排名相关"]
    B -->|按符号加权 / walk-forward| D["打分 score<br/>composite 或 ML"]
    D -->|每期 top-k 等权| E["组合回测<br/>vs 等权基准"]
    E --> F["可信度<br/>DSR / 跨市场 / 偏差量化"]
```

**关键区别**:旧路子在 A(单股时序)上建模,学不到"今天买 A 还是 B";`cross` 在 B(横截面面板)上建模,学的是**相对强弱**——这才是选股。

---

## 6. 设计约束 / Invariants

- **无未来函数**:因子只用过去;`fwd` 标签含未来仅用于训练/评估;walk-forward 训练末尾 purge 掉 `horizon` 天。由 `tests/test_cross.py::test_walk_forward_no_future_leak`(砍未来数据不改过去打分)焊死。
- **单一配置源**:所有路径/参数来自 `config.py`。
- **容错退回**:数据源失败自动降级(akshare→yfinance;Alpaca→yfinance;Claude→词典)。
- **缓存**:OHLCV/估值/面板均落盘缓存(`data/`),避免重复拉网。
- **可测试**:所有测试离线、合成数据、确定性;券商/情绪可注入 mock。
