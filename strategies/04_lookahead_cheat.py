# -*- coding: utf-8 -*-
"""
Day 2: a "peek at the future" cheating backtest (look-ahead bias)
=================================================================
Rule: if the price will go up "tomorrow," buy today; if it will drop tomorrow, stay in cash today.
This is obviously cheating -- you can't know tomorrow today. But this kind of bug is often
written by accident (shifting your data by one row does exactly this). Let's see how much
it can "earn."

Run: ./.venv/bin/python strategies/04_lookahead_cheat.py
"""
import ccxt
import pandas as pd

# Get the data
exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=720)
df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])

cash = 10_000.0
btc = 0.0
fee = 0.001

# Note: loop to len(df)-1 because we need to look at "tomorrow" (i+1)
for i in range(0, len(df) - 1):
    price_today    = df["Close"].iloc[i]
    price_tomorrow = df["Close"].iloc[i + 1]   # <- CHEATING! peeking at tomorrow's price

    will_go_up = price_tomorrow > price_today

    if will_go_up and btc == 0:
        # It'll rise tomorrow -> go all-in today
        btc = cash * (1 - fee) / price_today
        cash = 0.0
    elif (not will_go_up) and btc > 0:
        # It'll drop tomorrow -> sell everything today
        cash = btc * price_today * (1 - fee)
        btc = 0.0

final_value = cash + btc * df["Close"].iloc[-1]
return_pct = (final_value / 10_000 - 1) * 100
buy_hold_pct = (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100

print("===== Cheating version (peeking at tomorrow) results =====")
print(f"  Starting capital:  10000")
print(f"  Final value:       {final_value:,.0f}")
print(f"  Strategy return:   {return_pct:+,.0f}%")
print(f"  Buy & Hold bench:  {buy_hold_pct:+.0f}%")
