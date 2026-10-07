"""GDP growth analysis: CAGR from levels, volatility, recessions, decade averages and rankings.

Data are World Bank World Development Indicators loaded through ``core.worldbank``:

* ``NY.GDP.MKTP.KD.ZG``   GDP growth (annual %)
* ``NY.GDP.MKTP.KD``      GDP (constant 2015 US$)
* ``NY.GDP.PCAP.KD.ZG``   GDP per capita growth (annual %)
* ``NY.GDP.PCAP.KD``      GDP per capita (constant 2015 US$)

Window convention: a window ``(start, end)`` takes the **level at the end of
``start``** as the base. Growth rates are used for the years ``start + 1`` to
``end`` only, so the CAGR, the average, the volatility and the recession count
all describe the same ``end - start`` annual changes.

Run ``python projects/001-gdp-growth-dashboard/gdp_growth.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core import worldbank as wb
from core.stats import cagr

MEASURES = {
    "GDP": {
        "growth": "NY.GDP.MKTP.KD.ZG",
        "level": "NY.GDP.MKTP.KD",
        "level_label": "GDP (constant 2015 US$)",
        "growth_label": "GDP growth (annual %)",
    },
    "GDP per capita": {
        "growth": "NY.GDP.PCAP.KD.ZG",
        "level": "NY.GDP.PCAP.KD",
        "level_label": "GDP per capita (constant 2015 US$)",
        "growth_label": "GDP per capita growth (annual %)",
    },
}

DEFAULT_COUNTRIES = ["USA", "CHN", "IND", "GBR", "DEU", "JPN", "BRA"]
MIN_DECADE_OBS = 5


def load(measure: str = "GDP") -> pd.DataFrame:
    """Frame indexed by (iso3, year) with columns ``growth`` (%) and ``level`` (constant US$). Economies only."""
    codes = MEASURES[measure]
    return wb.indicators({"growth": codes["growth"], "level": codes["level"]})


def last_full_year(df: pd.DataFrame, share: float = 0.9) -> int:
    """Latest year in which at least ``share`` of the best-covered year's economies report growth."""
    per_year = df["growth"].dropna().groupby(level="year").size()
    return int(per_year[per_year >= share * per_year.max()].index.max())


def growth_in_window(df: pd.DataFrame, countries: list[str], start: int, end: int) -> pd.DataFrame:
    """Growth rates for the years start+1..end as a (year x country) frame; countries without data are kept as empty columns."""
    wide = df["growth"].unstack("iso3").reindex(columns=countries)
    return wide.loc[(wide.index > start) & (wide.index <= end)]


def _levels(df: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    return df["level"].unstack("iso3").reindex(columns=countries)


def window_cagr(df: pd.DataFrame, countries: list[str], start: int, end: int) -> pd.Series:
    """Compound annual growth rate (%) from the level in ``start`` to the level in ``end``; NaN if either is missing."""
    if end <= start:
        raise ValueError("end must be after start")
    levels = _levels(df, countries)
    out = {}
    for iso in countries:
        first = levels[iso].get(start, np.nan)
        last = levels[iso].get(end, np.nan)
        out[iso] = cagr(first, last, end - start) * 100 if pd.notna(first) and pd.notna(last) else np.nan
    return pd.Series(out, name="cagr_pct")


def recession_years(growth: pd.Series) -> list[int]:
    """Years with negative annual growth. Annual data cannot show quarterly 'technical' recessions."""
    return [int(y) for y in growth.index[growth < 0]]


def summary(df: pd.DataFrame, countries: list[str], start: int, end: int, names: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per country: CAGR, average growth, volatility, recessions and best/worst year for the window."""
    growth = growth_in_window(df, countries, start, end)
    cagrs = window_cagr(df, countries, start, end)
    rows = []
    for iso in countries:
        g = growth[iso].dropna()
        rows.append(
            {
                "iso3": iso,
                "country": (names or {}).get(iso, iso),
                "cagr_pct": cagrs[iso],
                "mean_growth_pct": g.mean() if len(g) else np.nan,
                "volatility_pp": g.std(ddof=1) if len(g) >= 3 else np.nan,
                "recession_years": int((g < 0).sum()),
                "worst_year": int(g.idxmin()) if len(g) else np.nan,
                "worst_growth_pct": g.min() if len(g) else np.nan,
                "best_year": int(g.idxmax()) if len(g) else np.nan,
                "best_growth_pct": g.max() if len(g) else np.nan,
                "years_with_data": len(g),
                "years_expected": end - start,
            }
        )
    return pd.DataFrame(rows)


def rank_economies(df: pd.DataFrame, start: int, end: int, *, min_start_level_bn: float = 0.0, names: dict[str, str] | None = None) -> pd.DataFrame:
    """All economies with a level in both ``start`` and ``end``, ranked by CAGR (1 = fastest).

    ``min_start_level_bn`` drops economies whose base-year level is below that many billions of constant US$,
    so that very small economies do not crowd the top of the ranking.
    """
    countries = sorted(df.index.get_level_values("iso3").unique())
    table = summary(df, countries, start, end, names)
    levels = _levels(df, countries)
    base = levels.loc[start] if start in levels.index else pd.Series(np.nan, index=countries)
    table["start_level_bn"] = table["iso3"].map(base) / 1e9
    table = table.dropna(subset=["cagr_pct"])
    table = table[table["start_level_bn"] >= min_start_level_bn]
    table = table.sort_values("cagr_pct", ascending=False).reset_index(drop=True)
    table["rank"] = np.arange(1, len(table) + 1)
    table["ranked_of"] = len(table)
    return table


def rebased_levels(df: pd.DataFrame, countries: list[str], start: int, end: int) -> pd.DataFrame:
    """Level of each country divided by its level in ``start`` x 100, for years start..end (tidy: year, iso3, index)."""
    levels = _levels(df, countries).loc[start:end]
    base = levels.loc[start] if start in levels.index else pd.Series(np.nan, index=countries)
    rebased = levels / base * 100
    return rebased.stack().rename("index").reset_index()


def decade_table(df: pd.DataFrame, countries: list[str], min_obs: int = MIN_DECADE_OBS) -> pd.DataFrame:
    """Mean of annual growth rates by decade (rows) and country (columns); NaN with fewer than ``min_obs`` years."""
    wide = df["growth"].unstack("iso3").reindex(columns=countries).dropna(how="all")
    decade = (wide.index // 10 * 10).astype(int)
    mean = wide.groupby(decade).mean()
    count = wide.groupby(decade).count()
    mean = mean.where(count >= min_obs)
    mean.index = [f"{d}s" for d in mean.index]
    return mean


def recession_table(df: pd.DataFrame, countries: list[str], start: int, end: int, names: dict[str, str] | None = None) -> pd.DataFrame:
    """Tidy list of recession years (negative growth) inside the window: country, year, growth_pct."""
    growth = growth_in_window(df, countries, start, end)
    rows = [
        {"country": (names or {}).get(iso, iso), "iso3": iso, "year": int(year), "growth_pct": value}
        for iso in countries
        for year, value in growth[iso].dropna().items()
        if value < 0
    ]
    return pd.DataFrame(rows, columns=["country", "iso3", "year", "growth_pct"]).sort_values(["country", "year"]).reset_index(drop=True)


def coverage(df: pd.DataFrame, countries: list[str], start: int, end: int, names: dict[str, str] | None = None) -> pd.DataFrame:
    """Per country: first and last year with growth data, and growth observations inside the window versus expected."""
    wide = df["growth"].unstack("iso3").reindex(columns=countries)
    in_window = growth_in_window(df, countries, start, end)
    rows = []
    for iso in countries:
        g = wide[iso].dropna()
        rows.append(
            {
                "country": (names or {}).get(iso, iso),
                "first_year": int(g.index.min()) if len(g) else np.nan,
                "last_year": int(g.index.max()) if len(g) else np.nan,
                "years_in_window": int(in_window[iso].notna().sum()),
                "years_expected": end - start,
            }
        )
    return pd.DataFrame(rows)


def world_coverage(df: pd.DataFrame) -> dict[str, int]:
    """Headline coverage numbers for the loaded measure."""
    g = df["growth"].dropna()
    per_year = g.groupby(level="year").size()
    return {
        "economies": int(g.index.get_level_values("iso3").nunique()),
        "first_year": int(per_year.index.min()),
        "last_year": int(per_year.index.max()),
        "economies_in_last_year": int(per_year.iloc[-1]),
        "last_full_year": last_full_year(df),
    }


def share_in_recession(df: pd.DataFrame, year: int) -> tuple[int, int]:
    """(economies with negative growth, economies reporting growth) in ``year``."""
    g = df["growth"].dropna().xs(year, level="year")
    return int((g < 0).sum()), int(len(g))


def main() -> None:
    names = wb.names()
    out = {}
    for measure in MEASURES:
        out[measure] = load(measure)
    df = out["GDP"]
    cov = world_coverage(df)
    start, end = 2000, cov["last_full_year"]
    print(f"Coverage (GDP growth): {cov}")

    table = summary(df, DEFAULT_COUNTRIES, start, end, names)
    cols = ["country", "cagr_pct", "mean_growth_pct", "volatility_pp", "recession_years", "worst_year", "worst_growth_pct"]
    print(f"\nWindow {start}-{end}, base = level in {start}")
    print(table[cols].round(2).to_string(index=False))

    ranking = rank_economies(df, start, end, min_start_level_bn=10, names=names)
    print(f"\nFastest CAGR {start}-{end} among {len(ranking)} economies with base GDP >= $10bn (2015 US$)")
    print(ranking.head(8)[["rank", "country", "cagr_pct", "start_level_bn"]].round(2).to_string(index=False))
    mine = ranking[ranking["iso3"].isin(DEFAULT_COUNTRIES)][["rank", "country", "cagr_pct"]]
    print("\nRanks of the default countries:")
    print(mine.round(2).to_string(index=False))

    all_rank = rank_economies(df, start, end, names=names)
    print(f"\nWithout the size filter: {len(all_rank)} economies, top 3 = {list(all_rank.head(3)['country'])}")

    gap = all_rank.assign(gap=all_rank["mean_growth_pct"] - all_rank["cagr_pct"]).sort_values("gap", ascending=False)
    print(f"\nAverage of annual growth rates minus CAGR, {len(gap)} economies (percentage points): "
          f"median {gap['gap'].median():.3f}, 90th percentile {gap['gap'].quantile(0.9):.3f}")
    print(gap.head(4)[["country", "mean_growth_pct", "cagr_pct", "gap", "volatility_pp"]].round(2).to_string(index=False))

    print("\nRecession years (negative growth) in the window:")
    for iso in DEFAULT_COUNTRIES:
        print(f"  {names[iso]}: {recession_years(growth_in_window(df, [iso], start, end)[iso].dropna())}")

    print("\nDecade averages (mean of annual growth, %):")
    print(decade_table(df, DEFAULT_COUNTRIES).round(1).to_string())

    for year in (2009, 2020):
        neg, total = share_in_recession(df, year)
        print(f"\n{year}: {neg} of {total} economies had negative GDP growth ({neg / total:.0%})")

    pc = out["GDP per capita"]
    pc_rank = rank_economies(pc, start, end, names=names)
    print(f"\nGDP per capita CAGR {start}-{end}: {len(pc_rank)} economies; "
          + ", ".join(f"{r.country} {r.cagr_pct:.2f}%" for r in pc_rank[pc_rank['iso3'].isin(['CHN', 'IND', 'USA'])].itertuples()))


if __name__ == "__main__":
    main()
