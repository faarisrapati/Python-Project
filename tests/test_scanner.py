"""Small offline checks for the screener's calculations and shortlist."""
from contextlib import redirect_stdout
from datetime import datetime
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import main as scanner


def sample_history(days=250):
    # Use recent dates so the scanner accepts this made-up price history.
    today = datetime.now(ZoneInfo("America/New_York")).date()
    dates = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=days)
    x = np.arange(days, dtype=float)
    return pd.DataFrame({"Close": 30 + x * 0.05 + np.sin(x / 3),
                         "Volume": np.full(days, 1_000_000.0)}, index=dates)


class ScreenerTests(unittest.TestCase):
    def test_volume_spike_uses_previous_twenty_days(self):
        data = sample_history()
        data.iloc[-1, data.columns.get_loc("Volume")] = 2_000_000
        result = scanner.analyze_stock(data, "TEST")
        self.assertEqual(result["RVOL"], 2)
        self.assertIn("Volume", result["Signals"])
        self.assertEqual(result["Score"], len(result["Signals"].split(", ")))
        self.assertEqual(data.columns.tolist(), ["Close", "Volume"])

    def test_short_history_and_zero_volume_are_skipped(self):
        self.assertIsNone(scanner.analyze_stock(sample_history(100), "IPO"))
        data = sample_history()
        data["Volume"] = 0
        self.assertIsNone(scanner.analyze_stock(data, "INACTIVE"))

    def test_price_filter_and_stale_history(self):
        data = sample_history()
        with patch.object(scanner, "MIN_PRICE", 1000):
            self.assertIsNone(scanner.analyze_stock(data, "TEST"))
        data.index = data.index - pd.Timedelta(days=30)
        self.assertIsNone(scanner.analyze_stock(data, "STALE"))

    def test_macd_transition_is_reflected_in_score(self):
        data = sample_history()
        above = pd.Series(1.0, index=data.index)
        below = pd.Series(-1.0, index=data.index)
        signal = pd.Series(0.0, index=data.index)
        with patch.object(scanner.ta, "MACD", return_value=(above, signal, above)):
            bullish = scanner.analyze_stock(data, "TEST")
        with patch.object(scanner.ta, "MACD", return_value=(below, signal, below)):
            bearish = scanner.analyze_stock(data, "TEST")
        self.assertEqual(bullish["Score"], bearish["Score"] + 1)
        self.assertIn("MACD", bullish["Signals"])
        self.assertNotIn("MACD", bearish["Signals"])

    def test_pipeline_skips_missing_symbol_and_saves_rankings(self):
        data = pd.concat({"TEST": sample_history()}, axis=1)
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(scanner, "TICKERS", ["TEST", "MISSING"]), \
                        patch.object(scanner.yf, "download", return_value=data), \
                        patch.object(scanner.yf, "set_tz_cache_location"), redirect_stdout(io.StringIO()) as output:
                    scanner.main()
                self.assertIn("1 stocks analyzed; 1 skipped", output.getvalue())
                self.assertEqual(pd.read_csv("all_results.csv").Ticker.tolist(), ["TEST"])
                self.assertEqual(pd.read_csv("shortlist.csv").Ticker.tolist(), ["TEST"])
            finally:
                os.chdir(original_directory)

    def test_shortlist_filters_weak_scores_and_sorts(self):
        row = scanner.analyze_stock(sample_history(), "TEST")
        rows = [dict(row, Ticker="WEAK", Score=2),
                dict(row, Ticker="WATCH", Score=3),
                dict(row, Ticker="STRONG", Score=4)]
        original_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with redirect_stdout(io.StringIO()):
                    scanner.show_results(rows)
                self.assertEqual(pd.read_csv("shortlist.csv").Ticker.tolist(), ["STRONG", "WATCH"])
                self.assertEqual(len(pd.read_csv("all_results.csv")), 3)
                with redirect_stdout(io.StringIO()) as output:
                    scanner.show_results([rows[0]])
                self.assertIn("weaker candidates", output.getvalue())
            finally:
                os.chdir(original_directory)

    def test_empty_results_do_not_claim_a_shortlist(self):
        with redirect_stdout(io.StringIO()) as output:
            scanner.show_results([])
        self.assertIn("No usable results", output.getvalue())


if __name__ == "__main__":
    unittest.main()
