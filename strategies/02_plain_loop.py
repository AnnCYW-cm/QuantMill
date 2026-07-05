# -*- coding: utf-8 -*-
"""
The same MA-crossover strategy -- but written as a plain Python for loop
========================================================================
Goal: let you fully see "what a backtest is actually doing."
There's no framework magic here -- just the for loops, if statements, and variables
you already know. Once you understand this, go back to the framework version in 01
and you'll see the framework just runs this loop for you automatically.

Run:
    cd ~/quant
    ./.venv/bin/python strategies/02_plain_loop.py
"""

import ccxt
import pandas as pd


# ---------- Step 1: get the data (same as 01) ----------
exchange = ccxt.binance()
print("Downloading BTC/USDT daily data...")
ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=720)
df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.date

# ---------- Step 2: compute the two moving averages ----------
# rolling(10).mean() = for each day, take the average of "the last 10 closes including today"
df["fast"] = df["Close"].rolling(10).mean()   # fast line: 10-day average
df["slow"] = df["Close"].rolling(30).mean()   # slow line: 30-day average


# ---------- Step 3: use a for loop to "pretend-trade" one day at a time ----------
cash = 10_000.0      # cash on hand (USD)
btc = 0.0            # how many BTC I hold (0 = in cash / no position)
fee = 0.001          # 0.1% trading fee
trades = []          # log every trade so we can review at the end

# Start from day 31 (the first 30 days have no MA yet -- values are NaN, so skip them)
for i in range(30, len(df)):
    price = df["Close"].iloc[i]          # today's close
    fast_today = df["fast"].iloc[i]      # today's fast line
    slow_today = df["slow"].iloc[i]      # today's slow line
    fast_yest = df["fast"].iloc[i - 1]   # yesterday's fast line
    slow_yest = df["slow"].iloc[i - 1]   # yesterday's slow line

    # "Golden cross": fast was at/below slow yesterday, rose above it today -> uptrend signal
    golden_cross = (fast_yest <= slow_yest) and (fast_today > slow_today)
    # "Death cross": fast was at/above slow yesterday, fell below it today -> downtrend signal
    death_cross = (fast_yest >= slow_yest) and (fast_today < slow_today)

    if golden_cross and btc == 0:
        # In cash and a golden cross appears -> convert all cash to BTC (buy)
        btc = cash * (1 - fee) / price   # after the fee, this is how many coins we can buy
        cash = 0.0
        trades.append((df["date"].iloc[i], "BUY", round(price, 1)))

    elif death_cross and btc > 0:
        # Holding and a death cross appears -> sell all BTC back to cash (sell)
        cash = btc * price * (1 - fee)   # proceeds after the fee
        btc = 0.0
        trades.append((df["date"].iloc[i], "SELL", round(price, 1)))


# ---------- Step 4: tally up and read the results ----------
# If we still hold BTC at the end, convert it to cash at the last day's price
final_value = cash + btc * df["Close"].iloc[-1]
return_pct = (final_value / 10_000 - 1) * 100

# Benchmark: what if we just bought on day 31 and held to the end (buy & hold)
buy_hold_pct = (df["Close"].iloc[-1] / df["Close"].iloc[30] - 1) * 100

print("\n===== Trade log =====")
for date, action, price in trades:
    print(f"  {date}  {action} @ {price}")

print("\n===== Results =====")
print(f"  Starting capital:  10000.00")
print(f"  Final value:       {final_value:.2f}")
print(f"  Strategy return:   {return_pct:+.2f}%")
print(f"  Buy & Hold bench:  {buy_hold_pct:+.2f}%   (losing to this = wasted effort)")
print(f"  Total trades:      {len(trades)}")
