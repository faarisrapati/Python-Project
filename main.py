"""A small Yahoo Finance stock screener. Run it with: python main.py"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import talib as ta
import yfinance as yf


# Edit this list to choose which stocks to scan.
TICKERS = [
    # Technology and semiconductors
    "AAPL", "MSFT", "NVDA", "AVGO", "AMD", "GOOGL", "META", "CRM", "ORCL", "ADBE",
    # Consumer businesses
    "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "COST", "WMT",
    # Finance
    "JPM", "BAC", "GS", "V", "MA", "AXP",
    # Healthcare
    "LLY", "JNJ", "ABBV", "MRK", "UNH", "AMGN",
    # Energy, industry
    "XOM", "CVX", "CAT", "DE", "GE", "HON", "PG", "KO", "PEP", "NEE",
]

# Change these settings without having to change the rest of the program.
TOP_RESULTS = 10
MIN_PRICE = 5
MIN_AVG_VOLUME = 300_000
RVOL_TARGET = 1.5


def analyze_stock(stock_data, ticker):
    """Calculate indicators and give one point for each bullish condition."""
    stock_data = stock_data.dropna(subset=["Close", "Volume"]).copy()
    stock_data = stock_data[(stock_data["Close"] > 0) & (stock_data["Volume"] >= 0)]
    stock_data = stock_data.sort_index()
    stock_data = stock_data[~stock_data.index.duplicated(keep="last")]
    if len(stock_data) < 201:
        return None  # The longest EMA needs 200 trading days to get started.

    # Exclude old histories, such as a stock that has stopped trading.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    age = (today - stock_data.index[-1].date()).days
    if age < 0 or age > 10:
        return None

    # EMAs give more weight to recent prices and help identify the trend.
    for period in [20, 50, 100, 200]:
        stock_data[f"EMA_{period}"] = ta.EMA(stock_data["Close"], timeperiod=period)

    # RSI measures momentum. We look for strength without an extreme reading.
    stock_data["RSI"] = ta.RSI(stock_data["Close"], timeperiod=14)

    # MACD above its signal line suggests positive momentum.
    stock_data["MACD"], stock_data["MACD_SIGNAL"], _ = ta.MACD(stock_data["Close"])

    # Compare the latest volume with the PREVIOUS 20 days, excluding that day.
    avg_volume = stock_data["Volume"].iloc[-21:-1].mean()
    latest = stock_data.iloc[-1]
    previous = stock_data.iloc[-2]
    if avg_volume <= 0 or pd.isna(latest[["EMA_200", "RSI", "MACD", "MACD_SIGNAL"]]).any():
        return None
    if latest["Close"] < MIN_PRICE or avg_volume < MIN_AVG_VOLUME:
        return None  # Skip stocks below our price or trading-volume minimums.
    rvol = latest["Volume"] / avg_volume

    # Each condition is worth one point, for a maximum score of four.
    trend_pass = (
        latest["Close"] > latest["EMA_20"] > latest["EMA_50"]
        > latest["EMA_100"] > latest["EMA_200"]
    )
    rsi_pass = 50 <= latest["RSI"] <= 70
    volume_pass = rvol >= RVOL_TARGET
    macd_pass = latest["MACD"] > latest["MACD_SIGNAL"]

    # Keeping the checks in a dictionary makes the score and explanation agree.
    checks = {"Uptrend": trend_pass, "RSI": rsi_pass,
              "Volume": volume_pass, "MACD": macd_pass}
    score = 0
    signals = []
    for name, passed in checks.items():
        if passed:
            score += 1
            signals.append(name)

    if score == 4:
        rating = "STRONG"
    elif score == 3:
        rating = "WATCH"
    elif score == 2:
        rating = "WEAK"
    else:
        rating = "LOW"

    return {
        "Ticker": ticker,
        "Date": stock_data.index[-1].date().isoformat(),
        "Price": round(latest["Close"], 2),
        "Change %": round((latest["Close"] / previous["Close"] - 1) * 100, 2),
        "Score": score,
        "Rating": rating,
        "RSI": round(latest["RSI"], 1),
        "RVOL": round(rvol, 2),
        "Signals": ", ".join(signals) or "None",
        "Yahoo Link": f"https://finance.yahoo.com/quote/{ticker}/",
    }


def show_results(results):
    """Print the shortlist and save two files that can be opened in Excel."""
    if not results:
        print("No usable results. Check the download messages or try again later.")
        return

    # Sort by score first. Relative volume breaks ties between equal scores.
    rankings = pd.DataFrame(results).sort_values(
        ["Score", "RVOL", "Ticker"], ascending=[False, False, True]
    )
    shortlist = rankings[rankings["Score"] >= 3].head(TOP_RESULTS)
    if shortlist.empty:
        print("\nNo stocks scored 3/4 or better. These are the highest ranked weaker candidates:")
        shortlist = rankings.head(TOP_RESULTS)
    else:
        print(f"\nSHORTLIST: {len(shortlist)} stocks scored at least 3/4")

    # Keep the terminal table compact; the CSV also includes dates and Yahoo links.
    columns = ["Ticker", "Price", "Change %", "Score", "Rating", "RSI", "RVOL", "Signals"]
    print(shortlist[columns].to_string(index=False))
    print("\nScore is out of 4. RVOL 1.5 means 1.5 times normal daily volume.")
    print("These are technical screening signals, not predictions.")

    # These files are replaced each time you run the scanner successfully.
    try:
        rankings.to_csv("all_results.csv", index=False)
        shortlist.to_csv("shortlist.csv", index=False)
        print("Saved shortlist.csv and all_results.csv. Open shortlist.csv to review the stocks.")
    except OSError as error:
        print(f"Could not save the CSV files: {error}")


def main():
    # Yahoo's local cache avoids fetching the same timezone information repeatedly.
    cache = Path(".scanner_cache/yfinance")
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))

    # One download call for 40 stocks, with no market-directory downloads or retries.
    # Excluding today's date avoids signals based on an unfinished trading session.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    print(f"Scanning {len(TICKERS)} stocks using daily bars before {today}...")
    try:
        data = yf.download(
            TICKERS, period="1y", interval="1d", end=today,
            group_by="ticker", auto_adjust=True, threads=4, progress=False, timeout=10,
        )
    except Exception as error:
        print(f"Yahoo Finance download failed: {error}")
        return

    results = []
    skipped = []
    for ticker in TICKERS:
        try:
            # Yahoo groups the price columns under each ticker's name.
            stock_data = data[ticker]
            result = analyze_stock(stock_data, ticker)
            if result is None:
                skipped.append(ticker)
            else:
                results.append(result)
        except (KeyError, ValueError, TypeError):
            skipped.append(ticker)  # One missing stock should not stop the scan.

    show_results(results)
    print(f"\n{len(results)} stocks analyzed; {len(skipped)} skipped (missing/stale data or filters).")
    if skipped:
        print("Skipped: " + ", ".join(skipped))


if __name__ == "__main__":
    main()
