"""FRED (St. Louis Fed) loader using the public CSV endpoint, with a committed cache.

    >>> from core import fred
    >>> cpi = fred.series("CPIAUCSL")                      # pandas Series, DatetimeIndex
    >>> df = fred.frame({"cpi": "CPIAUCSL", "wage": "AHETPI"})

No API key is needed. Cached as ``data/fred/<SERIES_ID>.csv.gz``.
"""

from __future__ import annotations

import io

import pandas as pd

from .http import get
from .paths import FRED_DIR

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _download(series_id: str) -> pd.Series:
    text = get(URL, params={"id": series_id}).text
    raw = pd.read_csv(io.StringIO(text))
    date_col = raw.columns[0]  # "observation_date" (new) or "DATE" (old)
    values = pd.to_numeric(raw[series_id], errors="coerce")
    out = pd.Series(values.to_numpy(), index=pd.to_datetime(raw[date_col]), name=series_id)
    out.index.name = "date"
    return out.dropna()


def series(series_id: str, *, refresh: bool = False) -> pd.Series:
    """One FRED series as a float Series with a DatetimeIndex (NaNs dropped)."""
    path = FRED_DIR / f"{series_id}.csv.gz"
    if path.exists() and not refresh:
        cached = pd.read_csv(path, parse_dates=["date"]).set_index("date")[series_id]
        return cached
    out = _download(series_id)
    FRED_DIR.mkdir(parents=True, exist_ok=True)
    out.reset_index().to_csv(path, index=False, compression="gzip")
    return out


def frame(ids: dict[str, str], *, refresh: bool = False) -> pd.DataFrame:
    """Several series side by side; keys of ``ids`` become the column names."""
    return pd.concat({name: series(sid, refresh=refresh) for name, sid in ids.items()}, axis=1).sort_index()
