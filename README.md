# Simple stock screener

Scan a fixed list of 40 stocks across several sectors with Yahoo Finance.
The stock list is a starting point you can edit, not a list of recommended buys.

```sh
python -m pip install -r requirements.txt
python main.py
```

The program downloads one year of daily history in one call. It uses bars
before today's New York date, so today's session is excluded even after close.

Each stock gets one point for each condition:

1. Price > EMA20 > EMA50 > EMA100 > EMA200: an established upward trend.
2. RSI14 between 50 and 70: positive momentum without an extreme reading.
3. Volume at least 1.5 times the previous 20 trading days' average.
4. MACD above its signal line: positive momentum.

Scores of 4 are **STRONG**, 3 are **WATCH**, 2 are **WEAK**, and 0–1 are **LOW**.
The shortlist shows up to 10 stocks scoring at least 3/4, ranked by score and
then relative volume. If none qualify, it clearly labels the highest ranked
weaker candidates instead. These are screening signals, not predictions.

The terminal shows prices, daily changes, scores, RSI, relative volume, and
which conditions passed. Two CSV files are saved in the project folder:

- `shortlist.csv`: the displayed shortlist, with dates and clickable Yahoo URLs.
- `all_results.csv`: every stock that could be analyzed and passed the filters.

Successful runs replace these files. If no stocks can be analyzed, existing
files remain from an earlier run; check their Date column.

Edit `TICKERS` at the top of `main.py` to change the stocks. Adjust `TOP_RESULTS`,
`MIN_PRICE`, `MIN_AVG_VOLUME`, or `RVOL_TARGET` directly below the list.
Stocks need at least 201 valid trading days, recent data (within 10 calendar
days), a price of at least $5, and average volume of at least 300,000 shares.
Skipped symbols are listed at the end. A full run makes about 40 symbol requests
through one download call; Yahoo/network delays can still affect runtime.

The code has three functions: `analyze_stock` calculates signals, `show_results`
prints and saves the rankings, and `main` downloads data and runs the scan.
Comments explain each step. There are no command-line options to configure.

Run the offline checks with:

```sh
python -m unittest discover -s tests -v
```
