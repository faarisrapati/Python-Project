# S&P 500 stock scanner

A Python stock scanner with a Streamlit dashboard. It gets daily prices from
Yahoo Finance, scores stocks using four technical indicators, and saves the results
to CSV files.

## Setup

From the project folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```


## Run

```sh
source .venv/bin/activate
python -m streamlit run dashboard.py
```

click **Run scan**. You can filter the results, look at stock charts, and view
previous scans. Keep the terminal open while using it. Press Control+C to stop.

To run the scanner without the dashboard:

```sh
python main.py
```

## Scoring

Each stock gets one point for each condition:

- Price > EMA20 > EMA50 > EMA100 > EMA200.
- RSI14 is between 50 and 70.
- Volume is at least 1.5 times the previous 20 trading days' average.
- MACD is above its signal line.

The shortlist shows up to 10 stocks scoring at least 3 out of 4. If none qualify,
it shows the highest-scoring weaker candidates instead. These are screening
signals, not predictions.

The scanner excludes today's trading session. Stocks with missing or stale data,
less than 201 valid trading days, prices below $5, or average volume below 300,000
shares are skipped. A full scan can take a few minutes.

## Saved results

- `shortlist.csv`: the latest shortlist.
- `all_results.csv`: all stocks that passed the data filters.


Running again on the same day replaces that day's results. Earlier days stay
saved. If a scan returns no usable results, existing files are left alone.
`Scan Date` is the day you ran it in New York; `Date` is the price-data date.
These files are ignored by Git, so back them up separately if you want to keep them.


```
