"""Cost of living: how much more does the same basket cost in one place than in another?

Two sources, kept apart on purpose:

* **US metropolitan areas** (a true city-level source): the Bureau of Economic Analysis regional price
  parities (RPPs), US government data in the public domain, 2008 onwards.
* **Countries** (the best open worldwide data): the World Bank price level index from the International
  Comparison Program, and The Economist's Big Mac index. Country figures are never presented as cities.

Every index is expressed with the national benchmark at 100 (US average for RPPs, United States for the
country measures), so "B relative to A" is simply the ratio of two index values.

Run ``python projects/005-cost-of-living-index/cost_of_living.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from core import bigmac
from core import worldbank as wb
from core.http import get
from core.paths import DATA

# ------------------------------------------------------------------ US metro areas (BEA)

BEA_URL = "https://apps.bea.gov/regional/zip/MARPP.zip"
BEA_PATH = DATA / "bea" / "MARPP_MSA.csv"
BEA_COMPONENTS = {1: "All items", 2: "Goods", 3: "Housing", 4: "Utilities", 5: "Other services"}
_BEA_NON_PLACES = {"00000", "00999"}  # the United States itself and its non-metropolitan remainder


def parse_bea(text: str) -> pd.DataFrame:
    """Tidy BEA ``MARPP`` table: geo_fips, metro, component, year, rpp (US average = 100).

    Footnote lines, the national total and the non-metropolitan remainder are dropped, and so are
    cells BEA marks ``(NA)`` (a few metro areas have no estimate before 2013-2016).
    """
    raw = pd.read_csv(io.StringIO(text), dtype=str)
    raw["geo_fips"] = raw["GeoFIPS"].str.strip().str.strip('"')
    raw = raw[raw["geo_fips"].str.fullmatch(r"\d{5}", na=False) & ~raw["geo_fips"].isin(_BEA_NON_PLACES)]
    year_columns = [c for c in raw.columns if c.isdigit()]
    raw = raw.assign(
        component=pd.to_numeric(raw["LineCode"]).map(BEA_COMPONENTS),
        metro=raw["GeoName"].str.replace(r"\s*\(?Metropolitan Statistical Area\)?\s*\*?\s*$", "", regex=True).str.strip(),
    )
    long = raw.melt(id_vars=["geo_fips", "metro", "component"], value_vars=year_columns, var_name="year", value_name="rpp")
    long["year"] = long["year"].astype(int)
    long["rpp"] = pd.to_numeric(long["rpp"].str.strip(), errors="coerce")
    long = long.dropna(subset=["rpp"])
    return long.sort_values(["geo_fips", "component", "year"]).reset_index(drop=True)


def load_bea(*, refresh: bool = False) -> pd.DataFrame:
    """BEA metro-area RPPs, downloaded once and cached under ``data/bea/``."""
    if not BEA_PATH.exists() or refresh:
        archive = zipfile.ZipFile(io.BytesIO(get(BEA_URL).content))
        member = next(n for n in archive.namelist() if n.startswith("MARPP_MSA_") and n.endswith(".csv"))
        BEA_PATH.parent.mkdir(parents=True, exist_ok=True)
        BEA_PATH.write_text(archive.read(member).decode("latin-1"), encoding="utf-8")
    return parse_bea(BEA_PATH.read_text(encoding="utf-8"))


def metro_panel(bea: pd.DataFrame) -> pd.DataFrame:
    """Panel indexed by (metro, year) with one column per price component."""
    panel = bea.pivot_table(index=["metro", "year"], columns="component", values="rpp")
    return panel.reindex(columns=list(BEA_COMPONENTS.values())).rename_axis(index=["place", "year"], columns=None)


# ------------------------------------------------------------------ countries (World Bank ICP, Big Mac)

WB_PRICE_LEVELS = {"household": "PA.NUS.PRVT.PLI", "gdp": "PA.NUS.GDP.PLI"}
COUNTRY_MEASURES = {
    "household": "Household consumption (World Bank)",
    "gdp": "Whole economy, GDP (World Bank)",
    "bigmac": "Big Mac (The Economist)",
}


def bigmac_levels() -> pd.DataFrame:
    """Big Mac price level, United States = 100: dollar price over the US dollar price, same release.

    The Economist publishes in January and July, so a country-year averages one or two releases. The euro
    area is dropped because it is a currency union, not a country.
    """
    raw = bigmac.load()
    us = raw.loc[raw["iso_a3"] == "USA"].set_index("date")["dollar_price"]
    raw = raw.assign(level=raw["dollar_price"] / raw["date"].map(us) * 100, year=raw["date"].dt.year)
    raw = raw[raw["iso_a3"] != "EUZ"]
    out = raw.groupby(["iso_a3", "year"], as_index=False).agg(bigmac=("level", "mean"), name=("name", "last"))
    return out.rename(columns={"iso_a3": "iso3"})


def country_table(*, refresh: bool = False) -> pd.DataFrame:
    """One row per country-year with the three price-level measures (United States = 100)."""
    levels = wb.indicators(WB_PRICE_LEVELS, refresh=refresh).reset_index()
    merged = levels.merge(bigmac_levels(), on=["iso3", "year"], how="outer")
    merged["country"] = merged["iso3"].map(wb.names()).fillna(merged["name"])
    cols = ["iso3", "country", "year", *COUNTRY_MEASURES]
    return merged[cols].dropna(subset=["country"]).sort_values(["iso3", "year"]).reset_index(drop=True)


def country_panel(table: pd.DataFrame) -> pd.DataFrame:
    """Panel indexed by (country, year) with one column per measure."""
    return table.set_index(["country", "year"])[list(COUNTRY_MEASURES)].rename_axis(index=["place", "year"])


def latest_year(panel: pd.DataFrame, measure: str, min_places: int = 150) -> int:
    """Latest year in which at least ``min_places`` places have a value for ``measure``."""
    counts = panel[measure].dropna().groupby(level="year").size()
    full = counts[counts >= min_places]
    return int(full.index.max() if len(full) else counts.index.max())


# ------------------------------------------------------------------ comparisons (work on either panel)


def snapshot(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    """Places in rows, measures in columns, for one year."""
    return panel.xs(year, level="year")


def relative_price(price_a: float, price_b: float) -> float:
    """How many times as expensive B is as A, from the two index values."""
    if not (price_a > 0 and price_b > 0):
        raise ValueError("index values must be positive")
    return price_b / price_a


def equivalent_salary(salary: float, price_a: float, price_b: float) -> float:
    """Salary in B with the same purchasing power over the index basket as ``salary`` in A.

    Both salaries are in the same currency units (US dollars at market exchange rates for the country
    measures), so ``equivalent_salary(60000, 100, 125)`` is 75,000: B costs 25% more, so you need 25% more.
    """
    return salary * relative_price(price_a, price_b)


def comparison(snap: pd.DataFrame, a: str, b: str) -> pd.DataFrame:
    """Index of A and B for every measure, and B's price level relative to A as a percentage difference."""
    for place in (a, b):
        if place not in snap.index:
            raise KeyError(f"{place!r} has no data for this year")
    out = pd.DataFrame({"A": snap.loc[a], "B": snap.loc[b]}).dropna()
    out["B_vs_A_pct"] = (out["B"] / out["A"] - 1) * 100
    return out.rename_axis("measure")


def rank_table(snap: pd.DataFrame, measure: str) -> pd.DataFrame:
    """All places with a value, rank 1 = most expensive, and the gap to the benchmark (100) in index points."""
    ranked = snap[measure].dropna().sort_values(ascending=False).rename("index").to_frame()
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    ranked["vs_100"] = ranked["index"] - 100
    return ranked.rename_axis("place").reset_index()


def history(panel: pd.DataFrame, places: list[str], measure: str) -> pd.DataFrame:
    """Long frame (place, year, value) for the chosen places."""
    series = panel[measure].dropna()
    series = series[series.index.get_level_values("place").isin(places)]
    return series.rename("value").reset_index()


def change_between(panel: pd.DataFrame, measure: str, start: int, end: int) -> pd.DataFrame:
    """Change in the index between two years, for places with a value in both."""
    wide = panel[measure].unstack("year")
    if start not in wide.columns or end not in wide.columns:
        raise KeyError(f"years {start} and {end} must both be in the data")
    out = wide[[start, end]].dropna()
    out.columns = ["start", "end"]
    out["change"] = out["end"] - out["start"]
    out["change_pct"] = (out["end"] / out["start"] - 1) * 100
    return out.sort_values("change", ascending=False).rename_axis("place").reset_index()


def spread(snap: pd.DataFrame) -> pd.DataFrame:
    """Highest, lowest and 90th-10th percentile range of each column, plus its correlation with the first column."""
    first = snap.columns[0]
    return pd.DataFrame(
        {
            "min": snap.min(),
            "max": snap.max(),
            "p90_minus_p10": snap.quantile(0.9) - snap.quantile(0.1),
            "corr_with_all_items": snap.corrwith(snap[first]),
        }
    )


def measure_agreement(snap: pd.DataFrame, a: str = "household", b: str = "bigmac") -> dict[str, float]:
    """How closely two price-level measures agree across the places that have both."""
    both = snap[[a, b]].dropna()
    return {
        "n": len(both),
        "spearman": float(both[a].corr(both[b], method="spearman")),
        "pearson": float(both[a].corr(both[b])),
        "median_ratio": float((both[b] / both[a]).median()),
    }


# ------------------------------------------------------------------ command line


def _show(frame: pd.DataFrame, **kwargs) -> str:
    return frame.round(1).to_string(index=False, **kwargs)


def main() -> None:
    bea = load_bea()
    panel = metro_panel(bea)
    metros = panel.index.get_level_values("place")
    years = panel.index.get_level_values("year")
    year = int(years.max())
    snap = snapshot(panel, year)
    print("US METRO AREAS (BEA regional price parities, US average = 100)")
    print(f"  {metros.nunique()} metropolitan areas, {years.min()}-{years.max()}; {len(snap)} with data in {year}")

    ranked = rank_table(snap, "All items")
    print(f"\nMost expensive, all items, {year}")
    print(_show(ranked.head(5)))
    print(f"\nLeast expensive, all items, {year}")
    print(_show(ranked.tail(5)))
    print(f"\nSpread across metros, {year}")
    print(spread(snap).round(2).to_string())

    a, b = "New York-Newark-Jersey City, NY-NJ", "Dallas-Fort Worth-Arlington, TX"
    cmp = comparison(snap, a, b)
    print(f"\n{a} vs {b}, {year}")
    print(cmp.round(1).to_string())
    print(f"  USD 100,000 in {a.split('-')[0]} buys what USD {equivalent_salary(100_000, snap.loc[a, 'All items'], snap.loc[b, 'All items']):,.0f} buys in Dallas")
    jackson = "Jackson, MS"
    print(f"  USD 100,000 in New York buys what USD {equivalent_salary(100_000, snap.loc[a, 'All items'], snap.loc[jackson, 'All items']):,.0f} buys in {jackson}")

    change = change_between(panel, "All items", int(years.min()), year)
    print(f"\nBiggest rises in the all-items index, {years.min()} to {year} (relative to the US average)")
    print(_show(change.head(4)))
    print("Biggest falls")
    print(_show(change.tail(4)))

    table = country_table()
    cp = country_panel(table)
    cy = latest_year(cp, "household")
    csnap = snapshot(cp, cy)
    print(f"\nCOUNTRIES (United States = 100), year {cy}")
    print(f"  household price level: {csnap['household'].notna().sum()} countries; GDP: {csnap['gdp'].notna().sum()}; Big Mac: {csnap['bigmac'].notna().sum()}")
    ranked = rank_table(csnap, "household")
    print("\nMost expensive, household consumption")
    print(_show(ranked.head(5)))
    print("\nLeast expensive, household consumption")
    print(_show(ranked.tail(5)))
    agree = measure_agreement(csnap)
    print(
        f"\nHousehold price level vs Big Mac, {agree['n']} countries: Spearman {agree['spearman']:.2f}, "
        f"Pearson {agree['pearson']:.2f}, median Big Mac / household = {agree['median_ratio']:.2f}"
    )
    for place in ("Switzerland", "India", "Germany"):
        eq = equivalent_salary(100_000, csnap.loc["United States", "household"], csnap.loc[place, "household"])
        print(f"  USD 100,000 in the United States matches USD {eq:,.0f} (market rates) in {place} (household basket, index {csnap.loc[place, 'household']:.1f})")

    change = change_between(cp, "household", 2010, cy)
    print(f"\nHousehold price level change 2010 to {cy} (relative to US prices)")
    print(_show(change.head(4)))
    print(_show(change.tail(4)))


if __name__ == "__main__":
    main()
