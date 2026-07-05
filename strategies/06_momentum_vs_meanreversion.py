# -*- coding: utf-8 -*-
"""
Day 4: Momentum vs Mean-Reversion -- two opposite strategies, same data
=======================================================================
Momentum (trend-following): price rises above the average -> buy (chase strength);
                            price falls below the average -> sell.
Mean-reversion (dip-buying): price drops far below the average -> buy (buy the dip);
                            price climbs back above the average -> sell.

They are mirror images: momentum buys exactly what mean-reversion sells.
No strategy is universally "good" -- each one is a tool matched to a market regime.

Run: ./.venv/bin/python strategies/06_momentum_vs_meanreversion.py
"""
import ccxt
import pandas as pd

exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=720)
df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
close = df["Close"].values
ma = df["Close"].rolling(20).mean().values     # 20-day moving average = the "normal level"
fee = 0.001                                     # 0.1% trading cost per trade (never skip this!)
N = 20                                          # skip first 20 days: the average isn't defined yet


def backtest(signal_fn):
    """signal_fn(i) returns True = should be holding, False = should be in cash.
    Returns (return %, max drawdown %, number of trades)."""
    cash, btc, trades = 10_000.0, 0.0, 0
    equity = []
    for i in range(N, len(df)):
        price = close[i]
        want_in = signal_fn(i)
        if want_in and btc == 0:                 # should hold but I'm in cash -> BUY
            btc = cash * (1 - fee) / price
            cash = 0.0
            trades += 1
        elif (not want_in) and btc > 0:          # should be in cash but I'm holding -> SELL
            cash = btc * price * (1 - fee)
            btc = 0.0
            trades += 1
        equity.append(cash + btc * price)        # net worth today = cash + value of BTC held

    ret = (equity[-1] / 10_000 - 1) * 100
    peak, max_dd = equity[0], 0.0
    for e in equity:                             # max drawdown: worst drop from a running peak
        peak = max(peak, e)
        max_dd = min(max_dd, (e - peak) / peak)
    return ret, max_dd * 100, trades


# --- Strategy 1: Momentum -- hold while price is above the average (ride the trend),
#     exit when it drops below. The entire strategy is this one line.
def momentum(i):
    return close[i] > ma[i]

# --- Strategy 2: Mean-reversion -- buy when price is 5%+ below the average (buy the dip),
#     sell once it climbs back above the average.
def mean_reversion(i):
    dev = (close[i] - ma[i]) / ma[i]      # how far price deviates from the average (negative = below)
    return dev < -0.05                     # more than 5% below the average -> want to hold (buy the dip)


# Benchmark: buy and hold
bh = (close[-1] / close[N] - 1) * 100

print(f"{'Strategy':<24}{'Return %':>10}{'MaxDD %':>10}{'# Trades':>10}")
print("-" * 54)
r, d, n = backtest(momentum)
print(f"{'Momentum (trend-follow)':<24}{r:>10.1f}{d:>10.1f}{n:>10}")
r, d, n = backtest(mean_reversion)
print(f"{'Mean-reversion (dip-buy)':<24}{r:>10.1f}{d:>10.1f}{n:>10}")
print("-" * 54)
print(f"{'Buy & Hold (benchmark)':<24}{bh:>10.1f}")
print("\nNote: the result depends on this window's market regime (trending vs choppy).")
print("The point isn't who wins -- it's understanding they have opposite personalities,")
print("each suited to a different kind of market.")
