"""A small Yahoo Finance stock screener. Run it with: python main.py"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json

import pandas as pd
import talib as ta
import yfinance as yf

from universe import load_constituents


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


def save_results(rankings, shortlist, scan_date, output_dir):
    """Save latest copies, daily snapshots, and one row per scan day and ticker."""
    output_dir = Path(output_dir)
    daily_dir = output_dir / "scans" / scan_date
    daily_dir.mkdir(parents=True, exist_ok=True)
    history_path = output_dir / "scans" / "history.csv"

    # Read history before writing anything, so an unreadable archive is preserved.
    history = pd.read_csv(history_path, keep_default_na=False) if history_path.exists() else pd.DataFrame()
    if not history.empty:
        if not {"Scan Date", "Ticker"}.issubset(history.columns):
            raise ValueError(f"{history_path} is missing Scan Date or Ticker columns")
        history = history[history["Scan Date"] != scan_date]
    history = pd.concat([history, rankings], ignore_index=True)
    history = history.sort_values(
        ["Scan Date", "Score", "RVOL", "Ticker"], ascending=[True, False, False, True]
    )

    for folder in [output_dir, daily_dir]:
        rankings.to_csv(folder / "all_results.csv", index=False, float_format="%.2f")
        shortlist.to_csv(folder / "shortlist.csv", index=False, float_format="%.2f")
    # Replace the history only after its complete contents have been written.
    temporary_path = history_path.with_suffix(".tmp")
    history.to_csv(temporary_path, index=False, float_format="%.2f")
    temporary_path.replace(history_path)
    print(f"\nLatest:   {output_dir / 'shortlist.csv'} | {output_dir / 'all_results.csv'}")
    print(f"Daily:    {daily_dir}/")
    print(f"History:  {history_path} ({len(history)} rows)")


def prepare_results(results, *, scan_date=None):
    """Build the same rankings for the terminal and dashboard."""
    scan_date = scan_date or datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    # Sort by score first. Relative volume breaks ties between equal scores.
    rankings = pd.DataFrame(results).sort_values(
        ["Score", "RVOL", "Ticker"], ascending=[False, False, True]
    )
    shortlist = rankings[rankings["Score"] >= 3].head(TOP_RESULTS)
    fallback = shortlist.empty
    if fallback:
        shortlist = rankings.head(TOP_RESULTS)

    rankings.insert(0, "Scan Date", scan_date)
    rankings["Shortlisted"] = rankings["Ticker"].isin(shortlist["Ticker"])
    rankings["Missing Signals"] = rankings["Signals"].apply(
        lambda signals: ", ".join(
            name for name in ["Uptrend", "RSI", "Volume", "MACD"]
            if name not in signals.split(", ")
        ) or "None"
    )
    shortlist = rankings.loc[shortlist.index]
    return rankings, shortlist, fallback


def show_results(results, *, scan_date=None, output_dir="."):
    """Display a readable shortlist and retain daily results across runs."""
    if not results:
        print("No usable results. Check the download messages or try again later.")
        return

    rankings, shortlist, fallback = prepare_results(results, scan_date=scan_date)
    scan_date = rankings["Scan Date"].iloc[0]

    print("\n" + "=" * 100)
    print(f"  STOCK SCREENER  |  Scan: {scan_date} (New York)")
    print(f"  Price data: {', '.join(sorted(rankings['Date'].unique()))}")
    counts = rankings["Rating"].value_counts()
    print(f"  Analyzed: {len(rankings)}  |  " + "  |  ".join(
        f"{rating}: {counts.get(rating, 0)}" for rating in ["STRONG", "WATCH", "WEAK", "LOW"]
    ))
    print("=" * 100)
    if fallback:
        print("No stocks scored 3/4 or better. Highest ranked weaker candidates:")
    else:
        print(f"SHORTLIST: {len(shortlist)} stocks scored at least 3/4")

    # Format only the display; keep numeric columns numeric in the CSV files.
    columns = ["Ticker", "Price", "Change %", "Score", "Rating", "RSI", "RVOL", "Signals"]
    display = shortlist[columns].copy()
    display.insert(0, "#", range(1, len(display) + 1))
    display["Price"] = display["Price"].map(lambda value: f"${value:,.2f}")
    display["Change %"] = display["Change %"].map(lambda value: f"{value:+.2f}%")
    display["Score"] = display["Score"].map(lambda value: f"{value}/4")
    display["RSI"] = display["RSI"].map(lambda value: f"{value:.1f}")
    display["RVOL"] = display["RVOL"].map(lambda value: f"{value:.2f}x")
    display = display.rename(columns={"Signals": "Passed checks"})
    print(display.to_string(index=False))
    print("-" * 100)
    print("Score: 4 STRONG | 3 WATCH | 2 WEAK | 0-1 LOW")
    print("RVOL: 1.50x = 1.5 times the previous 20 sessions' average volume.")
    print("These are technical screening signals, not predictions.")

    try:
        save_results(rankings, shortlist, scan_date, output_dir)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        print(f"Could not save the CSV files: {error}")


def run_scan(tickers, *, metadata=None, progress=None, output_dir=".", batch_size=40):
    """Download in bounded batches; return results and reasons for every skipped stock."""
    tickers = list(dict.fromkeys(tickers))
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    # Yahoo's local cache avoids fetching the same timezone information repeatedly.
    cache = Path(output_dir) / ".scanner_cache/yfinance"
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache))

    # Excluding today's date avoids signals based on an unfinished trading session.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    results = []
    skipped = {}
    details = metadata.set_index("Ticker").to_dict("index") if metadata is not None else {}
    for start in range(0, len(tickers), batch_size):
        batch = tickers[start:start + batch_size]
        try:
            data = yf.download(
                batch, period="2y", interval="1d", end=today,
                group_by="ticker", auto_adjust=True, threads=4, progress=False, timeout=10,
            )
        except Exception as error:
            skipped.update({ticker: f"Download failed: {error}" for ticker in batch})
        else:
            for ticker in batch:
                try:
                    stock_data = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
                    if stock_data.dropna(subset=["Close", "Volume"]).empty:
                        skipped[ticker] = "No price/volume data returned"
                        continue
                    result = analyze_stock(stock_data, ticker)
                    if result is None:
                        skipped[ticker] = "Insufficient/stale history or price/volume filters"
                    else:
                        result.update(details.get(ticker, {}))
                        results.append(result)
                except (KeyError, ValueError, TypeError) as error:
                    skipped[ticker] = f"Missing or unusable data: {error}"
        if progress:
            progress(min(start + len(batch), len(tickers)), len(tickers))
    return results, skipped


def save_scan_report(skipped, *, requested, universe, output_dir="."):
    """Retain scan coverage so a partial scan is visible on the dashboard."""
    report = {
        "Completed": datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
        "Universe": universe, "Requested": requested, "Skipped": skipped,
    }
    path = Path(output_dir) / "scans" / "latest_scan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(*, refresh_list=False):
    members = load_constituents(refresh=refresh_list)
    tickers = members.Ticker.tolist()
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    print(f"Scanning {len(tickers)} stocks using daily bars before {today}...")
    results, skipped = run_scan(
        tickers, metadata=members,
        progress=lambda done, total: print(f"Downloaded {done}/{total} symbols"),
    )

    show_results(results, scan_date=today)
    save_scan_report(skipped, requested=len(tickers), universe="S&P 500")
    print(f"\n{len(results)} stocks analyzed; {len(skipped)} skipped (missing/stale data or filters).")
    if skipped:
        print("Skipped: " + ", ".join(skipped))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan S&P 500 stocks with daily technical signals.")
    parser.add_argument("--refresh-list", action="store_true", help="Refresh S&P membership from the online source")
    options = parser.parse_args()
    main(refresh_list=options.refresh_list)
