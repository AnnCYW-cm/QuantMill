# -*- coding: utf-8 -*-
"""
First backtest: Moving-Average Crossover strategy (SMA Crossover)
=================================================================
This is the classic beginner strategy in quant trading, used to get the whole
pipeline running end to end:
    get data  ->  define rules  ->  backtest  ->  read results

Strategy rules (very simple -- the goal is to understand the flow, not to make money):
    - Compute two moving averages: a fast line (short, 10 days) and a slow line (long, 30 days)
    - Fast line crosses ABOVE slow line -> assume an uptrend is starting -> BUY
    - Fast line crosses BELOW slow line -> assume a downtrend is starting -> SELL

How to run (after installing dependencies):
    cd ~/quant
    ./.venv/bin/python strategies/01_first_backtest.py
"""

import ccxt
import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover, FractionalBacktest


# ----------------------------------------------------------------------
# Step 1: get the data
# Use ccxt to download historical daily BTC/USDT candles (free, no signup)
# ----------------------------------------------------------------------
def fetch_data(symbol="BTC/USDT", timeframe="1d", limit=720):
    """Download historical candles. limit=720 is roughly the last two years of daily data."""
    exchange = ccxt.binance()           # use Binance's public market-data endpoint
    print(f"Downloading {timeframe} data for {symbol}...")
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    # Each row ccxt returns is: [timestamp, Open, High, Low, Close, Volume]
    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]
    )
    # Convert the millisecond timestamp to a date and set it as the index
    # (backtesting.py requires a datetime index)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")
    print(f"Got {len(df)} candles, date range: {df.index[0].date()} ~ {df.index[-1].date()}")
    return df


# ----------------------------------------------------------------------
# Step 2: define the rules (as a strategy class)
# ----------------------------------------------------------------------
def SMA(values, n):
    """Simple moving average: the mean of the last n closing prices."""
    return pd.Series(values).rolling(n).mean()


class SmaCross(Strategy):
    # These two numbers are "parameters" -- you can tune them later
    n_fast = 10   # fast-line period
    n_slow = 30   # slow-line period

    def init(self):
        # Before the backtest starts, precompute both moving averages
        close = self.data.Close
        self.fast = self.I(SMA, close, self.n_fast)
        self.slow = self.I(SMA, close, self.n_slow)

    def next(self):
        # next() is called once per candle -- this is where we make buy/sell decisions
        if crossover(self.fast, self.slow):
            # fast line crosses above slow line -> buy with full position
            self.buy()
        elif crossover(self.slow, self.fast):
            # fast line crosses below slow line -> close all positions
            self.position.close()


# ----------------------------------------------------------------------
# Step 3: backtest + Step 4: read the results
# ----------------------------------------------------------------------
def main():
    data = fetch_data()

    # Use FractionalBacktest: allows buying "a fraction of a coin" (crypto supports decimal trading)
    # fractional_unit=1e-6 means the smallest tradable unit is 0.000001 coin -- fine enough
    bt = FractionalBacktest(
        data,
        SmaCross,
        cash=10_000,        # starting capital: $10,000
        commission=0.001,   # 0.1% fee per trade -- always include it, or the result is fake
        fractional_unit=1e-6,
    )
    stats = bt.run()

    print("\n" + "=" * 50)
    print("Backtest results:")
    print("=" * 50)
    # Print only the most important metrics
    key_metrics = [
        "Start", "End", "Return [%]", "Buy & Hold Return [%]",
        "Max. Drawdown [%]", "Sharpe Ratio", "# Trades", "Win Rate [%]",
    ]
    for k in key_metrics:
        print(f"{k:.<28} {stats[k]}")

    print("\nHow to read these:")
    print("- Return [%]            the strategy's final return")
    print("- Buy & Hold Return [%] what you'd make doing nothing, just holding (THE benchmark! losing to it = wasted effort)")
    print("- Max. Drawdown [%]     max drawdown -- worst peak-to-trough loss (smaller is better)")
    print("- Sharpe Ratio          return earned per unit of risk taken (>1 is decent)")
    print("- # Trades              total number of trades")

    # Save the equity curve chart -- open it in a browser
    bt.plot(filename="results/01_first_backtest.html", open_browser=False)
    print("\nEquity curve saved to: results/01_first_backtest.html (open it in a browser)")


if __name__ == "__main__":
    main()
