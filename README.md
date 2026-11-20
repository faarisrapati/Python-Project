# Fieldnote stock screener

Explore the S&P 500 through a local dashboard, or run the scanner in your terminal.
Both use the same calculations and save daily CSV files and long-term history.

## Open the dashboard

From the project folder:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run dashboard.py
```

Open the Local URL printed in the terminal, usually http://localhost:8501.
On macOS, you can also double-click `Open Dashboard.command` in Finder.
Keep the terminal running while using the dashboard; press Control+C to stop it.
The dashboard runs on your computer and writes directly to this project.

- Click **Run scan** to scan the S&P 500.
- Filter by sector, minimum score, ticker, or company name. Sort table columns
  by clicking their headings, and download the filtered results.
- Switch between the shortlist, all results, and full history. Use **View saved
  scan** to inspect an earlier day's files.
- Choose a stock to see passed/missed checks. **Load chart** downloads adjusted
  price history and draws EMA20, EMA50, and EMA200. This chart is fetched separately
  and may be newer than an archived scan.
- With at least two saved scan days, see score changes and new shortlist entries.
  A blank score change means the stock had no result on the previous scan day.
- Expand **Scan coverage and skipped stocks** to check whether the scan covered
  the full index. Data filters can exclude index members.
- Scanning again on the same day replaces that day's saved scan; earlier days
  remain intact.

## Run in the terminal

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Both the terminal scanner and dashboard scan the full S&P 500.

The program downloads two years of daily history in batches of up to 40 symbols,
with four download threads. It uses bars
before today's New York date, so today's session is excluded even after close.
Full-index scans can take several minutes depending on Yahoo and your connection.

## Index membership

`sp500_constituents.csv` is a bundled membership snapshot, initially downloaded
on November 19, 2026. The source is the
[datasets S&P 500 project](https://github.com/datasets/s-and-p-500-companies),
which derives membership from Wikipedia. It is not an official licensed index feed
and can lag membership changes. Separate share classes mean there can be more
than 500 ticker symbols. Company names and sectors are included in the results;
Yahoo symbols use hyphens for share classes, such as `BRK-B`.

Use **Refresh S&P 500 list** in the sidebar or run:

```sh
python main.py --refresh-list
```

The last saved list works offline. Refreshing requires internet access and only
replaces the file after validating the new list. Prices require Yahoo access;
existing scans can be viewed without downloading new prices.

## Signals and saved files

Each stock gets one point for each condition:

1. Price > EMA20 > EMA50 > EMA100 > EMA200: an established upward trend.
2. RSI14 between 50 and 70: positive momentum without an extreme reading.
3. Volume at least 1.5 times the previous 20 trading days' average.
4. MACD above its signal line: positive momentum.

Scores of 4 are **STRONG**, 3 are **WATCH**, 2 are **WEAK**, and 0–1 are **LOW**.
The shortlist shows up to 10 stocks scoring at least 3/4, ranked by score and
then relative volume. If none qualify, it clearly labels the highest ranked
weaker candidates instead. These are screening signals, not predictions.

The terminal shows a rating summary and an aligned table with dollar prices,
signed daily changes, scores out of four, RSI, relative volume, and passed checks.
CSV files keep numeric values suitable for sorting and analysis in a spreadsheet.
Run the program from this project folder; output paths are relative to the terminal's
current folder.

Two CSV files in the project folder always contain the latest successful scan:

- `shortlist.csv`: the displayed shortlist, with dates and clickable Yahoo URLs.
- `all_results.csv`: every stock that could be analyzed and passed the data,
  price, and average-volume filters, including low-scoring stocks.

Every successful run also saves daily snapshots and updates a long-term file:

```text
scans/
  2026-11-19/
    shortlist.csv
    all_results.csv
  2026-11-20/
    shortlist.csv
    all_results.csv
  history.csv
```

- The folder name and `Scan Date` column use the day you ran the scanner in
  New York. `Date` is the price-data date, which is earlier because the scanner
  excludes today's session. Weekends and holidays can share a price-data date.
- `history.csv` keeps all analyzed results across scan days. `Shortlisted` tells
  you whether each row appeared in that day's shortlist; `Missing Signals`
  explains which checks did not pass.
- Running again on the same day replaces that day's files and history rows,
  without adding duplicates. Earlier scan days stay in the history.
- Files are created only when you run the program; it does not run automatically.
- If no stocks can be analyzed, existing files remain from an earlier run;
  check `Scan Date` and `Date` before using them.

### Clearing results

You do not need to clear the list before a new scan: each successful run replaces
the latest results. To clear the visible latest results manually, delete only
the project-folder `shortlist.csv` and `all_results.csv`. They are recreated on
the next successful run; the archive stays intact.

For a complete fresh start, delete the `scans` folder as well. This permanently
removes your daily snapshots and long-term history, so copy it elsewhere first
if you want to keep it. Deleting a daily folder alone does not remove its rows
from `history.csv`.

The stock list comes from `sp500_constituents.csv`. Adjust `TOP_RESULTS`,
`MIN_PRICE`, `MIN_AVG_VOLUME`, or `RVOL_TARGET` directly below the list.
Stocks need at least 201 valid trading days, recent data (within 10 calendar
days), a price of at least $5, and average volume of at least 300,000 shares.
Skipped symbols are listed at the end. `scans/latest_scan.json` records the latest
scan attempt's requested coverage and skipped symbols. A partial successful scan
saves its usable results; check the coverage report when completeness matters.

`main.py` contains the reusable scanner and terminal entry point; `dashboard.py`
provides the Streamlit interface; `universe.py` loads and refreshes membership.

## Offline checks

```sh
python -m unittest discover -s tests -v
```
