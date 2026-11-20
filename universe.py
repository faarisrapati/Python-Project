"""S&P 500 membership snapshot with an explicit online refresh."""

from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

CONSTITUENTS_PATH = Path(__file__).resolve().parent / "sp500_constituents.csv"
CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "main/data/constituents.csv"
)


def validate_constituents(frame):
    required = ["Symbol", "Security", "GICS Sector"]
    if not set(required).issubset(frame.columns):
        raise ValueError("The membership file is missing symbol, company, or sector columns.")
    frame = frame[required].copy()
    if frame.isna().any().any() or not 450 <= len(frame) <= 550:
        raise ValueError("The membership file does not look like a complete S&P 500 list.")
    # Yahoo uses BRK-B and BF-B rather than the exchange's dotted notation.
    frame["Symbol"] = frame["Symbol"].str.strip().str.replace(".", "-", regex=False)
    if frame["Symbol"].duplicated().any() or not frame["Symbol"].str.fullmatch(r"[A-Z0-9-]+").all():
        raise ValueError("The membership file contains duplicate or invalid symbols.")
    return frame.rename(columns={"Symbol": "Ticker", "Security": "Company", "GICS Sector": "Sector"})


def load_constituents(*, refresh=False, path=CONSTITUENTS_PATH):
    """Use the bundled list offline; replace it only after a valid refresh."""
    path = Path(path)
    if refresh:
        request = Request(CONSTITUENTS_URL, headers={"User-Agent": "StockScreener/1.0"})
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8-sig")
        frame = validate_constituents(pd.read_csv(StringIO(raw)))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(raw, encoding="utf-8")
        temporary.replace(path)
        return frame
    return validate_constituents(pd.read_csv(path))
