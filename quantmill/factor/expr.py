# -*- coding: utf-8 -*-
"""
expr.py —— 因子表达式引擎(时序算子)| Factor expression engine (time-series operators)
=========================================================================================
让因子从"写死的 18 个"变成"一行表达式就能定义":
    "Close/Mean(Close,20)-1"      现价相对20日均线的偏离
    "Corr(Close,Volume,10)"       近10日价量相关
    "Rsi(Close,14)-Ref(Rsi(Close,14),5)"  RSI 5日变化

Turn factors from 18 hard-coded ones into one-line expressions.

⚠️ 铁律:所有算子只向后看(rolling / shift(正数)),绝无偷看未来。
⚠️ Iron rule: every operator looks backward only (rolling / positive shift). No look-ahead.

用法 / Usage:
    from quantmill.factor.expr import evaluate
    f = evaluate("Close/Mean(Close,20)-1", df)   # df 含 Open/High/Low/Close/Volume
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- 时序算子 | time-series ops
def Ref(x, n):
    """n 期之前的值(delay)。| Value n periods ago (delay). n>0 向后看 backward."""
    return x.shift(n)


def Delta(x, n):
    """与 n 期前的差。| Difference vs n periods ago."""
    return x - x.shift(n)


def Returns(x, n=1):
    """n 期收益率。| n-period percentage return."""
    return x.pct_change(n)


def Mean(x, n):
    """n 期滚动均值。| n-period rolling mean."""
    return x.rolling(n).mean()


def Std(x, n):
    """n 期滚动标准差。| n-period rolling std."""
    return x.rolling(n).std()


def Sum(x, n):
    """n 期滚动求和。| n-period rolling sum."""
    return x.rolling(n).sum()


def Tsmax(x, n):
    """n 期滚动最大值。| n-period rolling max."""
    return x.rolling(n).max()


def Tsmin(x, n):
    """n 期滚动最小值。| n-period rolling min."""
    return x.rolling(n).min()


def Tsrank(x, n):
    """当前值在过去 n 期里的分位(0~1)。| Rank of the current value within the past n periods."""
    return x.rolling(n).apply(lambda s: (s <= s[-1]).sum() / len(s), raw=True)


def Corr(x, y, n):
    """x、y 的 n 期滚动相关。| n-period rolling correlation of x and y."""
    return x.rolling(n).corr(y)


def Cov(x, y, n):
    """x、y 的 n 期滚动协方差。| n-period rolling covariance."""
    return x.rolling(n).cov(y)


def Skew(x, n):
    """n 期滚动偏度。| n-period rolling skewness."""
    return x.rolling(n).skew()


def Kurt(x, n):
    """n 期滚动峰度。| n-period rolling kurtosis."""
    return x.rolling(n).kurt()


def Ema(x, n):
    """n 期指数移动平均。| n-period exponential moving average."""
    return x.ewm(span=n, adjust=False).mean()


def Rsi(x, n=14):
    """RSI 相对强弱(0~100)。| RSI relative strength index."""
    delta = x.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


# ---------------------------------------------------------------- 逐元素算子 | element-wise ops
def Log(x):
    return np.log(x)


def Abs(x):
    return x.abs() if hasattr(x, "abs") else np.abs(x)


def Sign(x):
    return np.sign(x)


def Max(x, y):
    """逐元素取大。| element-wise max."""
    return np.maximum(x, y)


def Min(x, y):
    """逐元素取小。| element-wise min."""
    return np.minimum(x, y)


# 表达式里可用的算子命名空间 | operator namespace available inside expressions
_OPS = {
    "Ref": Ref, "Delay": Ref, "Delta": Delta, "Returns": Returns,
    "Mean": Mean, "Std": Std, "Sum": Sum, "Tsmax": Tsmax, "Tsmin": Tsmin,
    "Tsrank": Tsrank, "Corr": Corr, "Cov": Cov, "Skew": Skew, "Kurt": Kurt,
    "Ema": Ema, "Rsi": Rsi, "Log": Log, "Abs": Abs, "Sign": Sign,
    "Max": Max, "Min": Min, "np": np,
}

# 表达式里可直接引用的字段 | fields referenceable inside expressions
_FIELDS = ("Open", "High", "Low", "Close", "Volume")


def evaluate(expr: str, df: pd.DataFrame) -> pd.Series:
    """
    在一张 OHLCV 表上求值一个因子表达式,返回对齐的 Series。
    Evaluate a factor expression on an OHLCV table; return an index-aligned Series.

    安全性:受限命名空间(禁用内建),只暴露算子与 OHLCV 字段——用于开发者定义的因子表达式。
    Safety: restricted namespace (no builtins), only operators + OHLCV fields exposed.
    """
    ns = dict(_OPS)
    for f in _FIELDS:
        if f in df.columns:
            ns[f] = df[f]
    result = eval(expr, {"__builtins__": {}}, ns)  # noqa: S307 受限命名空间 | restricted ns
    # 标量(如常数表达式)广播成 Series;去掉 inf | broadcast scalars; scrub inf
    if not isinstance(result, pd.Series):
        result = pd.Series(result, index=df.index)
    return result.replace([np.inf, -np.inf], np.nan)
