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
                members = pd.DataFrame({"Ticker": ["TEST", "MISSING"],
                                        "Company": ["Test", "Missing"], "Sector": ["Technology", "Technology"]})
                with patch.object(scanner, "load_constituents", return_value=members), \
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

    def test_daily_snapshots_and_history_refresh_without_duplicates(self):
        row = scanner.analyze_stock(sample_history(), "TEST")
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            scanner.show_results([row, dict(row, Ticker="OTHER")],
                                 scan_date="2026-11-18", output_dir=folder)
            scanner.show_results([dict(row, Price=99)],
                                 scan_date="2026-11-19", output_dir=folder)
            scanner.show_results([dict(row, Price=101)],
                                 scan_date="2026-11-19", output_dir=folder)
            root = Path(folder)
            history = pd.read_csv(root / "scans/history.csv")
            self.assertEqual(len(history), 3)
            self.assertEqual(history[history["Scan Date"] == "2026-11-19"].Price.tolist(), [101])
            previous = root / "scans/2026-11-18/all_results.csv"
            self.assertEqual(len(pd.read_csv(previous)), 2)
            self.assertEqual(pd.read_csv(root / "all_results.csv").Price.tolist(), [101])
            self.assertTrue((root / "scans/2026-11-19/shortlist.csv").exists())
            self.assertFalse((root / "scans/history.tmp").exists())
            before = (root / "scans/history.csv").read_bytes()
            scanner.show_results([], scan_date="2026-11-20", output_dir=folder)
            self.assertEqual((root / "scans/history.csv").read_bytes(), before)
            self.assertFalse((root / "scans/2026-11-20").exists())

    def test_same_day_refresh_removes_stocks_missing_from_new_scan(self):
        row = scanner.analyze_stock(sample_history(), "TEST")
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            scanner.show_results([row, dict(row, Ticker="OTHER")], output_dir=folder)
            scanner.show_results([row], output_dir=folder)
            history = pd.read_csv(Path(folder) / "scans/history.csv")
            self.assertEqual(history.Ticker.tolist(), ["TEST"])

    def test_invalid_history_is_preserved(self):
        row = scanner.analyze_stock(sample_history(), "TEST")
        with tempfile.TemporaryDirectory() as folder:
            history_path = Path(folder) / "scans/history.csv"
            history_path.parent.mkdir()
            history_path.write_text("Unexpected\nkeep me\n")
            with redirect_stdout(io.StringIO()) as output:
                scanner.show_results([row], output_dir=folder)
            self.assertIn("Could not save", output.getvalue())
            self.assertEqual(history_path.read_text(), "Unexpected\nkeep me\n")

    def test_batched_scan_keeps_successes_when_another_batch_fails(self):
        data = pd.concat({"TEST": sample_history()}, axis=1)
        updates = []
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(scanner.yf, "download", side_effect=[data, RuntimeError("offline")]) as download, \
                patch.object(scanner.yf, "set_tz_cache_location"):
            results, skipped = scanner.run_scan(
                ["TEST", "MISSING", "FAILED"], batch_size=2, output_dir=folder,
                progress=lambda done, total: updates.append((done, total)),
            )
        self.assertEqual([row["Ticker"] for row in results], ["TEST"])
        self.assertEqual(set(skipped), {"MISSING", "FAILED"})
        self.assertIn("offline", skipped["FAILED"])
        self.assertEqual(download.call_count, 2)
        self.assertEqual(updates, [(2, 3), (3, 3)])

    def test_single_symbol_flat_columns_and_metadata(self):
        members = pd.DataFrame([{"Ticker": "TEST", "Company": "Example", "Sector": "Technology"}])
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(scanner.yf, "download", return_value=sample_history()), \
                patch.object(scanner.yf, "set_tz_cache_location"):
            results, skipped = scanner.run_scan(["TEST"], metadata=members, output_dir=folder)
        self.assertFalse(skipped)
        self.assertEqual(results[0]["Company"], "Example")

    def test_membership_contains_share_classes_and_all_sectors(self):
        members = scanner.load_constituents()
        self.assertGreater(len(members), 490)
        self.assertIn("BRK-B", members.Ticker.tolist())
        self.assertIn("BF-B", members.Ticker.tolist())
        self.assertEqual(members.Sector.nunique(), 11)

    def test_bad_membership_refresh_preserves_saved_list(self):
        from universe import CONSTITUENTS_PATH, load_constituents
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "members.csv"
            path.write_bytes(CONSTITUENTS_PATH.read_bytes())
            before = path.read_bytes()
            with patch("universe.urlopen") as response:
                response.return_value.__enter__.return_value.read.return_value = b"Symbol,Security,GICS Sector\nBAD,Bad,Unknown\n"
                with self.assertRaises(ValueError):
                    load_constituents(refresh=True, path=path)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
