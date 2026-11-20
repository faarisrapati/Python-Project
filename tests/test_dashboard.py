"""Exercise the local dashboard without live market requests."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from main import prepare_results, save_results
from universe import load_constituents

SOURCE = (Path(__file__).resolve().parents[1] / "dashboard.py").read_text()
ROW = {"Ticker": "AAPL", "Date": "2026-11-17", "Price": 150.5, "Change %": 1.2,
       "Score": 3, "Rating": "WATCH", "RSI": 60.0, "RVOL": 1.1,
       "Signals": "Uptrend, RSI, MACD", "Yahoo Link": "https://finance.yahoo.com/quote/AAPL/"}


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def save(self, rows, day):
        rankings, shortlist, _ = prepare_results(rows, scan_date=day)
        with redirect_stdout(io.StringIO()):
            save_results(rankings, shortlist, day, self.root)

    def app(self):
        source = SOURCE.replace('ROOT = Path(__file__).resolve().parent', f'ROOT = Path({str(self.root)!r})')
        return AppTest.from_string(source).run(timeout=15)

    def test_load_filters_and_historical_scan(self):
        self.save([dict(ROW, Score=2, Rating="WEAK")], "2026-11-18")
        self.save([ROW, dict(ROW, Ticker="MSFT", Score=4, Rating="STRONG")], "2026-11-19")
        app = self.app()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, "2")
        self.assertIn("Score change", app.dataframe[1].value.columns)
        app.text_input[0].set_value("MSFT").run()
        self.assertEqual(app.dataframe[1].value.Ticker.tolist(), ["MSFT"])
        app.text_input[0].set_value("no matching ticker").run()
        self.assertEqual(len(app.dataframe[1].value), 0)
        self.assertFalse(app.exception)
        app.text_input[0].set_value("").run()
        [s for s in app.selectbox if s.label == "View saved scan"][0].set_value("2026-11-18").run()
        self.assertEqual(app.metric[0].value, "1")
        self.assertTrue(any("weaker candidates" in warning.value for warning in app.warning))
        self.assertFalse(app.exception)

    def test_scan_button_saves_results_and_history(self):
        app = self.app()
        self.assertFalse(app.exception)
        with patch("main.run_scan", return_value=([ROW], {"BAD": "No data"})) as scan:
            [button for button in app.button if button.label == "Run scan"][0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(scan.call_args.args[0]), len(load_constituents()))
        self.assertEqual(pd.read_csv(self.root / "all_results.csv").Ticker.tolist(), ["AAPL"])
        self.assertTrue((self.root / "scans/history.csv").exists())
        self.assertTrue((self.root / "scans/latest_scan.json").exists())

    def test_failed_scan_keeps_previous_results(self):
        self.save([ROW], "2026-11-19")
        before = (self.root / "all_results.csv").read_bytes()
        app = self.app()
        with patch("main.run_scan", return_value=([], {"AAPL": "Offline"})):
            [button for button in app.button if button.label == "Run scan"][0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual((self.root / "all_results.csv").read_bytes(), before)
        self.assertTrue(any("Yahoo may be unavailable" in warning.value for warning in app.warning))

    def test_price_chart_loads_and_empty_download_is_reported(self):
        self.save([ROW], "2026-11-19")
        app = self.app()
        prices = pd.DataFrame({"Close": [100.0 + i for i in range(250)]},
                              index=pd.date_range("2025-01-01", periods=250))
        prices = pd.concat({"AAPL": prices}, axis=1).swaplevel(axis=1)
        with patch("yfinance.download", return_value=prices):
            [button for button in app.button if button.label == "Load chart for AAPL"][0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["price_chart"][0], "AAPL")
        self.assertEqual(len(app.session_state["price_chart"][1]), 126)
        with patch("yfinance.download", return_value=pd.DataFrame({"Close": []})):
            [button for button in app.button if button.label == "Load chart for AAPL"][0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("No chart data" in error.value for error in app.error))


if __name__ == "__main__":
    unittest.main()
