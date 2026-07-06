# 可插拔数据层 DataProvider / Pluggable data layer

把数据源从「焊死」变成「可插拔」——换成你自己的付费/机构数据,**不改任何调用点**。这是把 quantmill 从"研究底座"推向"真底座"的关键一层。

## 为什么

原来取数逻辑散在三处、各自硬编码(bars 在 `data`,基本面在 `cross/panel`,成分股在 `cross/universe`),回退 akshare→yfinance 焊死在函数里,PIT 靠调用方自觉。重构后:**四个单一职责接口 + 组合器 + 注册表**,数据源成为可替换零件。

## 四个接口(纯 pandas,契约由测试焊死)

`quantmill/data/provider.py`:

| 接口 | 方法 | 返回(契约) |
|---|---|---|
| `BarSource` | `bars(symbol, market, start, end)` | `[Open,High,Low,Close,Volume]` + 升序 DatetimeIndex |
| `FundamentalSource` | `fundamentals(symbol, market, start, end)` | 业务列 + **`available_date`**(该值公开可用之日,含披露滞后)= PIT |
| `UniverseSource` | `universe(market, index, asof)` | `[symbol, in_date, out_date]`,只含 `in_date ≤ asof`(无幸存/前视偏差) |
| `QuoteSource` | `quotes(symbols, market)` | index=symbol,含 `price` |

provider **按需实现**能实现的接口(akshare 实现 3 个、yfinance 实现 2 个),不必全实现。

## 组合与注册

- `ChainSource([a, b])` —— 依次尝试,失败回退(替掉焊死的 akshare→yfinance)。
- `CachingSource(inner)` —— 包一个 BarSource 加本地缓存(默认 CSV,沿用现有缓存;可换 `_ParquetBarStore`)。
- `Registry` —— 按 `(能力, 市场)` 解析已组装好的源;默认在 `data/__init__.py::_build_registry()` 构建。

调用点仍是老门面,**一行没改**:`get_ohlcv()` / `fundamentals()` / `universe_df()` / `quotes()` 底层都走 `REGISTRY`。

## 换源:一个环境变量

```bash
# A股 bars 优先用你自己的 parquet 数据,回退 yfinance(逗号=回退链)
export QUANTMILL_BARS_CN=parquet,yfinance
# 基本面换成你的源(需你实现并注册到 _PROVIDERS)
export QUANTMILL_FUNDAMENTALS_CN=myvendor
```
格式:`QUANTMILL_<能力>_<市场>=provider1,provider2`(能力 = BARS/FUNDAMENTALS/UNIVERSE/QUOTES)。

## 已内置样板:SharadarProvider(PIT 干净的美股)

`data/sharadar.py` 是"接付费数据修天花板"的头号样板(经 Nasdaq Data Link),**四接口全实现**:

| 接口 | Sharadar 表 | 为什么关键 |
|---|---|---|
| `bars` | SEP | 复权日线(`closeadj`,O/H/L 同因子缩放) |
| `fundamentals` | SF1(dim=ARQ) | **`datekey`=SEC 备案日=天然 `available_date`** → 严格 PIT 基本面(免费源没有) |
| `universe` | SP500 | **含 added/removed 动作 → 真实成分史,survivorship-free**(填平 hk/us 天花板) |
| `quotes` | SEP 末行 | 最新收盘 |

用法:
```bash
pip install -e ".[sharadar]"
echo "NASDAQ_DATA_LINK_API_KEY=你的key" > ~/quant/.sharadar   # 或设环境变量
export QUANTMILL_BARS_US=sharadar,yfinance          # 美股 bars 优先 Sharadar
export QUANTMILL_FUNDAMENTALS_US=sharadar           # 解锁美股基本面(平台原来没有)
export QUANTMILL_UNIVERSE_US=sharadar               # 用真实 S&P500 成分史,不再幸存者偏差
```
> ⚠️ 这是**模板**:列名按 Sharadar 官方 schema 映射、映射逻辑有离线测试焊死(`tests/test_sharadar.py`),
> 但作者无真实账号未跑通端到端;接上你的 key 后若某列名有出入,改 `_MAP_SF1` 即可。

## 接入你自己的数据(三步)

**A. 最快:用自带的 `ParquetProvider` 模板(零代码)**
1. `pip install -e ".[parquet]"`(装 pyarrow)。
2. 把你的日线放到 `data/custom/<market>_<symbol>.parquet`(列含 OHLCV,索引为日期)。
3. `export QUANTMILL_BARS_CN=parquet,yfinance` —— 有自备数据就用,没有回退 yfinance。

**B. 写你自己的 provider(接 Wind/彭博/自有库)**
```python
class MyVendor:
    name = "myvendor"
    def markets(self): return {"cn"}
    def bars(self, symbol, market, start, end):
        df = ...            # 你的取数;返回 [Open,High,Low,Close,Volume] + DatetimeIndex
        return df
# 注册:在 data/__init__.py 的 _PROVIDERS 里加 "myvendor": MyVendor()
# 然后 export QUANTMILL_BARS_CN=myvendor
```

**C. 用契约测试确保你的 provider 合规**
```python
from quantmill.data.provider import assert_bar_contract, assert_fundamental_contract
assert_bar_contract(MyVendor(), "600519", "cn", "2023-01-01", "2024-01-01")
# 基本面源必须带 available_date 且不早于数据日,否则测试直接拦下(防未来函数)
```

## 同款:可插拔 ModelProvider(AI 能力集成)

模型层照同一套哲学做成可插拔(`quantmill/model/provider.py`)——数据、LLM、**模型**三层同构。

- **契约**:`fit(X, y) -> self` + `predict(X) -> 实数分数`(越大越看多;分类器=P涨∈[0,1],回归器=预测收益)。
- **按任务两个注册表**:`CLASSIFIERS`(单股 P涨)/ `REGRESSORS`(横截面打分)。
- **自带实现**:`lgbm`(默认,与原写死参数逐值等价——零回归)、`logistic`、`ridge`(sklearn,证明可插拔)。
- **换模型一个环境变量**:
  ```bash
  export QUANTMILL_MODEL_RANKER=ridge      # 横截面打分器(cross)
  export QUANTMILL_MODEL_CLF=logistic      # 单股分类器
  ```
- **接你自己的模型**(XGBoost / 神经网 / LLM-as-ranker):写个类实现 `fit/predict`、
  `REGRESSORS.register(你的类)`,过 `assert_model_contract` 即可——和接数据源一样。

## 现状与边界(诚实标注)

- ✅ bars(cn/hk/us)、fundamentals(cn/hk)、universe(**cn/hk/us 全走注册表**)。
- ✅ **严格 PIT 已接**:`build_panel` 用 `_pit_align`(`merge_asof(available_date, backward)`)——
  每个交易日只用当日**已公开**的估值;接带真实披露滞后的财报源不会泄露未来(测试焊死)。
  无 `available_date` 的老缓存自动退化为 `reindex+ffill`(等价原行为)。
- ⚠️ **hk/us universe 是【当前】蓝筹静态清单,带幸存者偏差** —— 这不是没做完,是**免费数据的天花板本身**:
  真实 PIT 成分史(含被踢出的股票)无免费源。已诚实标注,且**现在可被替换**:实现一个
  `UniverseSource` 注册到对应市场即可(`QUANTMILL_UNIVERSE_HK`)。cn 用真实成分+纳入日期(半修:
  含"后纳入"前视的修复,仍缺"被踢出"的那半,需付费 PIT)。
- bars 缓存默认仍是 CSV(沿用已缓存的数百只,零失效);parquet store 可选。
