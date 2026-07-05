# -*- coding: utf-8 -*-
"""
Plot the real BTC price + both moving averages + golden/death cross points, save as an image.
Run: ./.venv/bin/python strategies/03_plot_ma.py
"""
import ccxt
import pandas as pd
import matplotlib.pyplot as plt

# Get the data
exchange = ccxt.binance()
ohlcv = exchange.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=720)
df = pd.DataFrame(ohlcv, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
df["date"] = pd.to_datetime(df["ts"], unit="ms")
df["fast"] = df["Close"].rolling(10).mean()
df["slow"] = df["Close"].rolling(30).mean()

# Find the golden-cross / death-cross positions
df["golden"] = (df["fast"].shift(1) <= df["slow"].shift(1)) & (df["fast"] > df["slow"])
df["death"]  = (df["fast"].shift(1) >= df["slow"].shift(1)) & (df["fast"] < df["slow"])

# Take a representative window (150 days) -- too long and it turns into a blur
window = df.iloc[120:270].copy()

# Plot
plt.figure(figsize=(14, 7))
plt.plot(window["date"], window["Close"], color="#bbbbbb", linewidth=1, label="Price (Close)")
plt.plot(window["date"], window["fast"], color="#ff7f0e", linewidth=1.6, label="Fast MA (10d)")
plt.plot(window["date"], window["slow"], color="#1f77b4", linewidth=1.6, label="Slow MA (30d)")

# Golden cross: green up-triangle; death cross: red down-triangle
g = window[window["golden"]]
d = window[window["death"]]
plt.scatter(g["date"], g["fast"], marker="^", s=180, color="green", zorder=5, label="Golden Cross (BUY)")
plt.scatter(d["date"], d["fast"], marker="v", s=180, color="red",   zorder=5, label="Death Cross (SELL)")

plt.title("BTC/USDT - Moving Average Crossover (Fast 10d vs Slow 30d)", fontsize=14)
plt.ylabel("Price (USDT)")
plt.legend(loc="upper left")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig("results/03_ma_chart.png", dpi=120)
print("Chart saved to results/03_ma_chart.png")
print(f"In this window: {len(g)} golden crosses, {len(d)} death crosses")
