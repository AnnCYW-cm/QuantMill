# -*- coding: utf-8 -*-
"""
Day 3: adding "risk management" to the MA strategy -- stop-loss + position sizing, comparing max drawdown
========================================================================================================
Same golden-cross-buy / death-cross-sell strategy, run in three versions to see how risk control saves you:
  Version A: full position, no stop-loss    (the rawest, most dangerous)
  Version B: full position + 8% stop-loss
  Version C: half position + 8% stop-loss   (the most robust)

Run: ./.venv/bin/python strategies/05_risk_management.py
"""
import ccxt
import pandas as pd

# ---------- Get data + compute moving averages ----------
exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=720)
df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
df["fast"] = df["Close"].rolling(10).mean()
df["slow"] = df["Close"].rolling(30).mean()
close = df["Close"].values
fast = df["fast"].values
slow = df["slow"].values
fee = 0.001


def run(stop_loss=None, position_fraction=1.0):
    """
    stop_loss:         stop-loss size, e.g. 0.08 means sell if it drops 8%; None means no stop-loss
    position_fraction: what fraction of cash to deploy each time, 1.0 = full, 0.5 = half
    Returns (total return %, max drawdown %, number of trades)
    """
    cash = 10_000.0
    btc = 0.0
    entry_price = None       # record the buy price, used to compute the stop-loss level
    equity_curve = []        # total assets each day, used to compute drawdown
    trades = 0

    for i in range(30, len(df)):
        price = close[i]

        # --- Weapon 1: check the stop-loss first ---
        # While holding, if price falls below "entry price x (1 - stop_loss)", sell immediately
        if btc > 0 and stop_loss is not None and price <= entry_price * (1 - stop_loss):
            cash += btc * price * (1 - fee)
            btc = 0.0
            trades += 1

        # --- MA signals ---
        golden = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        death  = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]

        if golden and btc == 0:
            # --- Weapon 2: deploy only part of the cash to buy, keep the rest as cash ---
            invest = cash * position_fraction
            btc = invest * (1 - fee) / price
            cash -= invest
            entry_price = price
            trades += 1
        elif death and btc > 0:
            cash += btc * price * (1 - fee)
            btc = 0.0
            trades += 1

        # Record total assets at today's close (cash + value of BTC held)
        equity_curve.append(cash + btc * price)

    # ---------- Compute total return ----------
    final = equity_curve[-1]
    ret = (final / 10_000 - 1) * 100

    # ---------- Compute max drawdown ----------
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e                      # new all-time high
        dd = (e - peak) / peak            # how far below the peak we are right now (negative)
        if dd < max_dd:
            max_dd = dd
    return ret, max_dd * 100, trades


print(f"{'Version':<24}{'Return %':>10}{'MaxDD %':>10}{'# Trades':>10}")
print("-" * 54)
for name, sl, pf in [
    ("A full pos, no stop",   None, 1.0),
    ("B full pos, 8% stop",   0.08, 1.0),
    ("C half pos, 8% stop",   0.08, 0.5),
]:
    ret, dd, n = run(stop_loss=sl, position_fraction=pf)
    print(f"{name:<24}{ret:>10.1f}{dd:>10.1f}{n:>10}")

print("\nWhat to notice: comparing A->B->C, the return barely changes (even dips slightly),")
print("but the MAX DRAWDOWN clearly shrinks.")
print("Risk control isn't about earning more -- it's about losing less at the worst moment,")
print("so you can hold on and not get knocked out of the game.")
