"""Run with: python -m streamlit run dashboard.py"""

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import talib as ta
import yfinance as yf

from main import prepare_results, run_scan, save_results, save_scan_report
from universe import load_constituents

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Fieldnote · Stock scanner", page_icon="📈", layout="wide")
st.markdown("""
<style>
  .stApp {background: #f4f7fb;}
  [data-testid="stSidebar"] {background: #101e32;}
  [data-testid="stSidebar"] * {color: #edf3fa;}
  [data-testid="stSidebar"] button *, [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] [data-baseweb="select"] * {color: #17283e;}
  .block-container {padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1500px;}
  h1, h2, h3 {color: #14253d; letter-spacing: -0.025em;}
  [data-testid="stMetric"] {background: white; border: 1px solid #dfe7f0;
    border-radius: 12px; padding: 16px 20px;}
  [data-testid="stMetricLabel"] {color: #52647a;}
  [data-testid="stMetricValue"] {color: #14253d;}
  .eyebrow {color: #137866; font-weight: 700; letter-spacing: .14em; font-size: .875rem;}
</style>
""", unsafe_allow_html=True)


def read_csv(path):
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, keep_default_na=False)
    except (OSError, ValueError) as error:
        st.error(f"Could not read {path.name}: {error}")
        return pd.DataFrame()


def add_metadata(frame, members):
    if frame.empty:
        return frame
    lookup = members.set_index("Ticker")
    frame = frame.copy()
    for column in ["Company", "Sector"]:
        mapped = frame["Ticker"].map(lookup[column]).fillna("Unknown")
        if column not in frame:
            frame[column] = mapped
        else:
            frame[column] = frame[column].replace("", pd.NA).fillna(mapped)
    return frame


def download_button(label, frame, filename, key):
    st.download_button(label, frame.to_csv(index=False).encode("utf-8"),
                       filename, "text/csv", key=key)


try:
    members = load_constituents()
except (OSError, ValueError) as error:
    st.error(f"Cannot load the S&P 500 membership list: {error}")
    st.stop()

with st.sidebar:
    st.markdown("## FIELDNOTE")
    st.caption("Your daily market research desk")
    st.divider()
    st.markdown("### S&P 500")
    tickers = members.Ticker.tolist()
    st.caption(f"{len(tickers)} symbols · daily price bars")
    scan_clicked = st.button("Run scan", type="primary", width="stretch")
    st.caption("S&P 500 scans can take several minutes. Keep this tab open.")
    st.divider()
    if st.button("Refresh S&P 500 list", width="stretch"):
        try:
            with st.spinner("Updating index membership…"):
                load_constituents(refresh=True)
            st.success("Membership list updated.")
            st.rerun()
        except Exception as error:
            st.error(f"Refresh failed; the saved membership list is unchanged. {error}")
    st.caption("Membership uses the datasets project’s Wikipedia-derived snapshot.")
    st.link_button("Membership source", "https://github.com/datasets/s-and-p-500-companies")
    st.divider()
    st.caption("Daily files and long-term history are saved in your project’s scans folder.")

st.markdown('<div class="eyebrow">MARKET RESEARCH / DAILY SCREENER</div>', unsafe_allow_html=True)
st.title("Find strength. Follow the changes.")
st.write("Explore technical signals across the S&P 500, then keep a record of what changed.")

if scan_clicked:
    with st.status(f"Scanning {len(tickers)} symbols…", expanded=True) as status:
        progress = st.progress(0, text="Preparing downloads…")
        try:
            results, skipped = run_scan(
                tickers, metadata=members, output_dir=ROOT,
                progress=lambda done, total: progress.progress(
                    done / total, text=f"Processed {done} of {total} symbols"
                ),
            )
            if results:
                rankings, shortlist, _ = prepare_results(results)
                with redirect_stdout(io.StringIO()):
                    save_results(rankings, shortlist, rankings["Scan Date"].iloc[0], ROOT)
                save_scan_report(skipped, requested=len(tickers), universe="S&P 500", output_dir=ROOT)
                status.update(label=f"Saved {len(results)} results · {len(skipped)} skipped",
                              state="complete", expanded=False)
            else:
                status.update(label="No usable results. Your saved results were preserved.", state="error")
                st.warning("Yahoo may be unavailable, or no stocks passed the data filters. Try again later.")
            if skipped:
                st.session_state["last_skipped"] = skipped
            else:
                st.session_state.pop("last_skipped", None)
        except Exception as error:
            status.update(label="The scan could not finish", state="error")
            st.error(str(error))

latest = read_csv(ROOT / "all_results.csv")
history = read_csv(ROOT / "scans/history.csv")
archive_dates = sorted(
    [path.name for path in (ROOT / "scans").glob("????-??-??")
     if (path / "all_results.csv").exists()], reverse=True
)
selected_date = st.selectbox("View saved scan", ["Latest results"] + archive_dates)
folder = ROOT if selected_date == "Latest results" else ROOT / "scans" / selected_date
rankings = add_metadata(latest if selected_date == "Latest results" else read_csv(folder / "all_results.csv"), members)
shortlist = add_metadata(read_csv(folder / "shortlist.csv"), members)

if rankings.empty:
    st.info("Your research desk is ready. Click Run scan to scan the S&P 500 and generate results.")
    st.stop()
required = {"Ticker", "Date", "Price", "Change %", "Score", "Rating", "RSI", "RVOL", "Signals"}
if not required.issubset(rankings.columns):
    st.error("The saved results have an older or invalid format. Run a new scan to regenerate them.")
    st.stop()

scan_day = str(rankings["Scan Date"].iloc[0]) if "Scan Date" in rankings else "Unknown"
st.caption(f"SCAN DATE  {scan_day}  ·  PRICE DATA  {', '.join(sorted(rankings['Date'].unique()))}"
           "  ·  Today’s trading session is excluded")
today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
if scan_day != today:
    st.info("You are viewing a saved scan. Click Run scan to request updated results.")
if selected_date == "Latest results" and len(rankings) < 100:
    st.info(f"The saved scan contains {len(rankings)} analyzed stocks. Click Run scan for full-index coverage.")

previous = pd.DataFrame()
if not history.empty and {"Scan Date", "Ticker", "Score", "Shortlisted"}.issubset(history.columns):
    older = history[history["Scan Date"] < scan_day]
    if not older.empty:
        previous = older[older["Scan Date"] == older["Scan Date"].max()]
        prior_scores = previous.set_index("Ticker")["Score"]
        rankings["Score change"] = rankings["Score"] - rankings["Ticker"].map(prior_scores)
        previous_picks = set(previous.loc[previous["Shortlisted"].astype(str).str.lower() == "true", "Ticker"])
        new_picks = set(shortlist.Ticker) - previous_picks if not shortlist.empty else set()
        rankings["New to shortlist"] = rankings["Ticker"].isin(new_picks)
        st.caption(f"Score changes compare with the saved scan from {previous['Scan Date'].iloc[0]}. "
                   "Blank changes mean the stock had no analyzed result in that scan.")

metrics = st.columns(5)
for column, label, value in zip(metrics, ["Analyzed", "Strong · 4/4", "Watch · 3/4", "Shortlisted", "Sectors"],
                                [len(rankings), int((rankings.Score == 4).sum()),
                                 int((rankings.Score == 3).sum()), len(shortlist), rankings.Sector.nunique()]):
    column.metric(label, value)

st.write("")
with st.container(border=True):
    st.subheader("Your screening workspace")
    filters = st.columns([2, 2, 1])
    query = filters[0].text_input("Find a stock", placeholder="Ticker or company name")
    sectors = filters[1].multiselect("Sectors", sorted(rankings.Sector.unique()))
    minimum = filters[2].slider("Minimum score", 0, 4, 0)
    filtered = rankings[rankings.Score >= minimum]
    if sectors:
        filtered = filtered[filtered.Sector.isin(sectors)]
    if query:
        filtered = filtered[filtered.Ticker.str.contains(query, case=False, regex=False) |
                            filtered.Company.str.contains(query, case=False, regex=False)]

    picks_tab, all_tab, history_tab = st.tabs(["Shortlist", "All results", "Long-term history"])
    visible_columns = ["Ticker", "Company", "Sector", "Price", "Change %", "Score", "Rating",
                       "Score change", "New to shortlist", "RSI", "RVOL", "Signals", "Missing Signals", "Yahoo Link"]
    column_config = {
        "Price": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
        "Change %": st.column_config.NumberColumn("Daily change (%)", format="%.2f%%"),
        "Score": st.column_config.ProgressColumn("Score / 4", min_value=0, max_value=4, format="%d"),
        "Score change": st.column_config.NumberColumn("Score change", format="%+d"),
        "RVOL": st.column_config.NumberColumn("Relative volume", format="%.2fx"),
        "Yahoo Link": st.column_config.LinkColumn("Research", display_text="Yahoo Finance"),
    }
    for tab, is_shortlist in [(picks_tab, True), (all_tab, False)]:
        with tab:
            visible = filtered[filtered.Ticker.isin(shortlist.Ticker)] if is_shortlist and not shortlist.empty else filtered
            if is_shortlist and shortlist.empty:
                visible = filtered.iloc[0:0]
            if is_shortlist and not shortlist.empty and shortlist.Score.max() < 3:
                st.warning("No stocks qualified at 3/4 or higher. This shortlist shows weaker candidates.")
            st.caption(f"{len(visible)} matching stocks · click a column heading to sort")
            st.dataframe(visible[[c for c in visible_columns if c in visible]],
                         column_config=column_config, hide_index=True, width="stretch")
            download_button("Download these results", visible,
                            f"{'shortlist' if is_shortlist else 'all_results'}_{scan_day}.csv",
                            f"download_{is_shortlist}")
    with history_tab:
        st.write("One entry per stock per scan day. Running again on the same day refreshes that day’s results.")
        if history.empty:
            st.info("History appears after the first successful scan.")
        else:
            st.caption("This table contains all saved days and is independent of the filters above.")
            st.dataframe(history.sort_values(["Scan Date", "Score"], ascending=[False, False]),
                         hide_index=True, width="stretch", column_config=column_config)
            download_button("Download full history", history, "scanner_history.csv", "history_download")

st.subheader("Look closer")
if filtered.empty:
    st.info("No stocks match your filters. Broaden the filters to see stock details.")
else:
    ticker = st.selectbox("Choose a stock", filtered.Ticker.tolist(),
                          format_func=lambda symbol: f"{symbol} · {rankings.loc[rankings.Ticker == symbol, 'Company'].iloc[0]}")
    row = rankings.loc[rankings.Ticker == ticker].iloc[0]
    detail, chart = st.columns([1, 2])
    with detail, st.container(border=True):
        st.subheader(ticker)
        st.write(row.Company)
        st.metric("Adjusted closing price", f"${row.Price:,.2f}", f"{row['Change %']:+.2f}%")
        checks = {
            "Uptrend": "Price > EMA20 > EMA50 > EMA100 > EMA200",
            "RSI": "RSI14 between 50 and 70",
            "Volume": "Volume at least 1.5 times the previous 20-session average",
            "MACD": "MACD above its signal line",
        }
        for name, explanation in checks.items():
            passed = name in str(row.Signals).split(", ")
            st.write(f"{'✅' if passed else '➖'} **{name}** — {explanation}")
        st.link_button("Open Yahoo Finance", f"https://finance.yahoo.com/quote/{ticker}/")
    with chart, st.container(border=True):
        st.subheader("Price and trend")
        st.caption("Load an adjusted daily-price chart from Yahoo. The chart can be newer than a saved scan.")
        if st.button(f"Load chart for {ticker}"):
            try:
                with st.spinner("Loading chart…"):
                    price_data = yf.download(ticker, period="2y", end=today, auto_adjust=True,
                                             progress=False, threads=False, timeout=10)
                    if isinstance(price_data.columns, pd.MultiIndex):
                        price_data = price_data.xs(ticker, axis=1, level=1)
                    close = price_data["Close"].dropna()
                    if close.empty:
                        raise ValueError("No chart data returned. Try again later.")
                    plot = pd.DataFrame({"Close": close})
                    for period in [20, 50, 200]:
                        plot[f"EMA {period}"] = ta.EMA(close, timeperiod=period)
                    st.session_state["price_chart"] = (ticker, plot.tail(126))
            except Exception as error:
                st.error(f"Chart unavailable: {error}")
        cached_chart = st.session_state.get("price_chart")
        if cached_chart and cached_chart[0] == ticker:
            st.line_chart(cached_chart[1], y_label="Adjusted price ($)", height=300)
        if not history.empty and {"Ticker", "Scan Date", "Score"}.issubset(history.columns):
            stock_history = history[history.Ticker == ticker].sort_values("Scan Date")
            if len(stock_history) > 1:
                st.caption("Score across your saved scan days")
                st.line_chart(stock_history.set_index("Scan Date")[["Score"]], height=170)
            else:
                st.info("Run scans on more days to see this stock’s score history.")

with st.expander("Scan coverage and skipped stocks"):
    report_path = ROOT / "scans/latest_scan.json"
    if selected_date == "Latest results" and report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            st.write(f"Last completed attempt: {report['Completed']} · {report['Universe']} · {report['Requested']} requested")
            skipped = report["Skipped"]
            if skipped:
                st.dataframe(pd.DataFrame(skipped.items(), columns=["Ticker", "Reason"]), hide_index=True)
            else:
                st.write("No symbols were skipped.")
        except (OSError, ValueError, KeyError) as error:
            st.warning(f"Coverage report unavailable: {error}")
    else:
        st.write("No coverage report is available for this saved scan.")
    if st.session_state.get("last_skipped"):
        st.caption("Skipped symbols from your most recent scan attempt in this session")
        st.dataframe(pd.DataFrame(st.session_state["last_skipped"].items(), columns=["Ticker", "Reason"]), hide_index=True)

with st.expander("How to read the scanner"):
    st.write("Each stock earns one point for each passed check. 4 = STRONG, 3 = WATCH, 2 = WEAK, 0–1 = LOW. "
             "The shortlist contains up to 10 qualifying stocks, ordered by score and then relative volume. "
             "If none qualify, it shows the best weaker candidates and labels them.")
    st.write("Stocks need at least 201 valid trading sessions, recent data, a price of at least $5, "
             "and average daily volume of at least 300,000 shares. Technical signals are not predictions.")
st.caption("FIELDNOTE · Daily research, saved over time · Prices are adjusted historical data, not live quotes.")
