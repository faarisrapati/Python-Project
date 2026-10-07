# All the libraries and imports to run my project
import yfinance as yf
import pandas as pd
import numpy as np
import talib as ta
import matplotlib.pyplot as plt
import seaborn as sns


def main():

    # Starting with a couple of stocks to test the waters
    tickers = ["AAPL", "MSFT", "NVDA"]

    # Two years of data for 200 moving average
    data = yf.download(
        tickers,
        period="2y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
    )

    # Go through each stock
    for ticker in tickers:

        stock_data = data[ticker].dropna()
        stock_data = stock_data.copy()

        # Calculate EMAs
        for period in [20, 50, 100, 200]:

            stock_data[f"EMA_{period}"] = ta.EMA(
                stock_data["Close"],
                timeperiod=period,
            )

        # Calculate RSI
        stock_data["RSI_14"] = ta.RSI(
            stock_data["Close"],
            timeperiod=14,
        )
        # Calculate the average volume over the last 20 days
        stock_data["AVG_VOLUME_20"] = stock_data["Volume"].rolling(20).mean()
        stock_data["RVOL"] = (
        stock_data["Volume"] / stock_data["AVG_VOLUME_20"]
        )

        # Get the most recent trading day
        latest = stock_data.iloc[-1]
        volume_pass = latest["RVOL"] >= 1.5

        # Check if EMAs are stacked bullishly
        trend_pass = (
            latest["Close"] > latest["EMA_20"]
            and latest["EMA_20"] > latest["EMA_50"]
            and latest["EMA_50"] > latest["EMA_100"]
            and latest["EMA_100"] > latest["EMA_200"]
        )

        # Check RSI
        rsi_pass = 50 <= latest["RSI_14"] <= 70

        # Display information
        print("\n" + "=" * 40)
        print(f"{ticker:^40}")
        print("=" * 40)

        print(f"Price:          ${latest['Close']:.2f}")
        print(f"EMA 20:         ${latest['EMA_20']:.2f}")
        print(f"EMA 50:         ${latest['EMA_50']:.2f}")
        print(f"EMA 100:        ${latest['EMA_100']:.2f}")
        print(f"EMA 200:        ${latest['EMA_200']:.2f}")
        print(f"RSI (14):        {latest['RSI_14']:.2f}")
        print(f"Volume:          {latest['Volume']:,.0f}")
        print(f"Avg Volume:      {latest['AVG_VOLUME_20']:,.0f}")
        print(f"Relative Volume: {latest['RVOL']:.2f}x")

        print()
        print(f"Trend:          {'PASS' if trend_pass else 'FAIL'}")
        print(f"RSI:            {'PASS' if rsi_pass else 'FAIL'}")
        print(f"RVOL:           {'PASS' if volume_pass else 'FAIL'}")

        print("-" * 40)

        if trend_pass and rsi_pass and volume_pass:
            print("OVERALL:        PASS")
        else:
            print("OVERALL:        FAIL")

        print("=" * 40)


if __name__ == "__main__":
    main()