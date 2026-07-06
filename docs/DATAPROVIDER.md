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

## 现状与边界(诚实标注)

- ✅ bars(cn/hk/us)、fundamentals(cn/hk)、universe(cn 真实成分+纳入日期)已走注册表。
- ⚠️ **universe 的 hk/us 仍是 `cross/universe` 的静态蓝筹清单**(未接真实成分史),这一半待补。
- ⚠️ `available_date` 对百度估值=当日(比率由当日价算得,当日可知);接**带真实披露滞后的财报源**时,`build_panel` 应从 `reindex+ffill` 升级为 `merge_asof(available_date)` 才算严格 PIT——接口已留好这个位。
- bars 缓存默认仍是 CSV(沿用已缓存的数百只,零失效);parquet store 可选。
