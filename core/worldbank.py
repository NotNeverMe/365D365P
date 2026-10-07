"""World Bank Indicators API loader with a committed on-disk cache.

    >>> from core import worldbank as wb
    >>> gdp = wb.indicator("NY.GDP.MKTP.KD.ZG")          # tidy: iso3, country, year, value
    >>> wide = wb.indicators({"growth": "NY.GDP.MKTP.KD.ZG", "pop": "SP.POP.TOTL"})
    >>> countries = wb.countries()                        # region, income group, is_aggregate

Data are cached as ``data/worldbank/<code>.csv.gz``. Pass ``refresh=True`` (or
delete the file) to download again.
"""

from __future__ import annotations

import pandas as pd

from .http import DataUnavailable, get
from .paths import WORLDBANK_DIR

API = "https://api.worldbank.org/v2"
COLUMNS = ["iso3", "country", "year", "value"]


def _paginate(url: str, params: dict) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        payload = get(url, params={**params, "format": "json", "per_page": 20000, "page": page}).json()
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            message = payload[0].get("message") if payload and isinstance(payload[0], dict) else payload
            raise DataUnavailable(f"World Bank API returned no data for {url}: {message}")
        meta, data = payload
        rows.extend(data)
        if page >= int(meta.get("pages", 1)):
            return rows
        page += 1


def _download_indicator(code: str) -> pd.DataFrame:
    rows = _paginate(f"{API}/country/all/indicator/{code}", {})
    frame = pd.DataFrame(
        {
            "iso3": [r["countryiso3code"] for r in rows],
            "country": [r["country"]["value"] for r in rows],
            "year": [int(r["date"]) for r in rows],
            "value": [r["value"] for r in rows],
        }
    )
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["value"])
    frame = frame[frame["iso3"].astype(str).str.len() == 3]
    return frame.sort_values(["iso3", "year"]).reset_index(drop=True)[COLUMNS]


def indicator(code: str, *, refresh: bool = False) -> pd.DataFrame:
    """Tidy frame (iso3, country, year, value) for one indicator, all economies."""
    path = WORLDBANK_DIR / f"{code}.csv.gz"
    if path.exists() and not refresh:
        return pd.read_csv(path)
    frame = _download_indicator(code)
    WORLDBANK_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    return frame


def indicators(codes: dict[str, str], *, refresh: bool = False, economies_only: bool = True) -> pd.DataFrame:
    """Wide frame indexed by (iso3, year) with one column per name in ``codes``.

    ``codes`` maps a friendly column name to a World Bank indicator code.
    Aggregates such as ``WLD`` or ``EUU`` are dropped unless
    ``economies_only=False``.
    """
    parts = []
    for name, code in codes.items():
        part = indicator(code, refresh=refresh).set_index(["iso3", "year"])["value"].rename(name)
        parts.append(part)
    wide = pd.concat(parts, axis=1).sort_index()
    if economies_only:
        keep = set(countries().query("not is_aggregate")["iso3"])
        wide = wide[wide.index.get_level_values("iso3").isin(keep)]
    return wide


def countries(*, refresh: bool = False) -> pd.DataFrame:
    """Country metadata: iso3, name, region, income_group, is_aggregate."""
    path = WORLDBANK_DIR / "_countries.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path)
    rows = _paginate(f"{API}/country", {})
    frame = pd.DataFrame(
        {
            "iso3": [r["id"] for r in rows],
            "name": [r["name"] for r in rows],
            "region": [r["region"]["value"].strip() for r in rows],
            "income_group": [r["incomeLevel"]["value"].strip() for r in rows],
        }
    )
    frame["is_aggregate"] = frame["region"].eq("Aggregates")
    WORLDBANK_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def names() -> dict[str, str]:
    """Map iso3 -> country name for real economies."""
    meta = countries().query("not is_aggregate")
    return dict(zip(meta["iso3"], meta["name"]))
