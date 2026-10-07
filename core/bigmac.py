"""The Economist's Big Mac index (full version), cached locally.

Source: https://github.com/TheEconomist/big-mac-data (CC-BY). One row per
country per release date (January/July), 2000 onwards.
"""

from __future__ import annotations

import pandas as pd

from .http import get
from .paths import BIGMAC_DIR

URL = "https://raw.githubusercontent.com/TheEconomist/big-mac-data/master/output-data/big-mac-full-index.csv"
PATH = BIGMAC_DIR / "big-mac-full-index.csv"


def load(*, refresh: bool = False) -> pd.DataFrame:
    if not PATH.exists() or refresh:
        BIGMAC_DIR.mkdir(parents=True, exist_ok=True)
        PATH.write_bytes(get(URL).content)
    frame = pd.read_csv(PATH, parse_dates=["date"])
    return frame.sort_values(["iso_a3", "date"]).reset_index(drop=True)
