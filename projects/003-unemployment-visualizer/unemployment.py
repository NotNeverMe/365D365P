"""Unemployment by country, gender, age and education, with gaps and coverage.

World Bank World Development Indicators, loaded through ``core.worldbank``:

* ``SL.UEM.TOTL.ZS`` / ``SL.UEM.TOTL.FE.ZS`` / ``SL.UEM.TOTL.MA.ZS``  total, female, male (% of labour force), ILO modelled estimates
* ``SL.UEM.1524.ZS``                                                     youth, ages 15-24 (% of the youth labour force), ILO modelled estimates
* ``SL.UEM.BASC.ZS`` / ``SL.UEM.INTM.ZS`` / ``SL.UEM.ADVN.ZS``            basic, intermediate, advanced education
                                                                         (% of the labour force with that education), ILO Education and Mismatch Indicators

Derived measures (all in the same units as the inputs):

* ``gender_gap``      female minus male unemployment rate, in percentage points (positive: women worse off)
* ``youth_ratio``     youth rate divided by the all-ages (15+) rate. The all-ages rate includes the young, so this
                      understates the youth-to-adult (25+) ratio, which the World Bank does not publish.
* ``education_gap``   basic minus advanced education unemployment rate, in percentage points
                      (positive: the less educated are worse off; negative: graduates are)

Run ``python projects/003-unemployment-visualizer/unemployment.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

import pandas as pd

from core import worldbank as wb

INDICATORS = {
    "total": "SL.UEM.TOTL.ZS",
    "female": "SL.UEM.TOTL.FE.ZS",
    "male": "SL.UEM.TOTL.MA.ZS",
    "youth": "SL.UEM.1524.ZS",
    "basic": "SL.UEM.BASC.ZS",
    "intermediate": "SL.UEM.INTM.ZS",
    "advanced": "SL.UEM.ADVN.ZS",
}
LABELS = {
    "total": "Total (15+)",
    "female": "Female",
    "male": "Male",
    "youth": "Youth (15-24)",
    "basic": "Basic education",
    "intermediate": "Intermediate education",
    "advanced": "Advanced education",
    "gender_gap": "Gender gap, female minus male (pp)",
    "youth_ratio": "Youth rate / all-ages rate",
    "education_gap": "Education gap, basic minus advanced (pp)",
}
EDUCATION = ["basic", "intermediate", "advanced"]
MAX_EDUCATION_AGE = 5  # how many years back an education observation may be and still stand in for the selected year


def load() -> pd.DataFrame:
    """Frame indexed by (iso3, year): the seven rates plus ``gender_gap``, ``youth_ratio`` and ``education_gap``. Economies only."""
    df = wb.indicators(INDICATORS)
    df["gender_gap"] = df["female"] - df["male"]
    df["youth_ratio"] = df["youth"] / df["total"]
    df["education_gap"] = df["basic"] - df["advanced"]
    return df


def economy_count() -> int:
    """Number of real economies (not aggregates) in the World Bank country list."""
    return len(wb.names())


def coverage_table(df: pd.DataFrame, n_economies: int) -> pd.DataFrame:
    """For each input series: economies covered, observations, first/last year, and how many years a typical economy has."""
    rows = []
    for col in INDICATORS:
        s = df[col].dropna()
        per_economy = s.groupby(level="iso3").size()
        rows.append(
            {
                "series": LABELS[col],
                "indicator": INDICATORS[col],
                "economies": len(per_economy),
                "share_of_economies_pct": 100 * len(per_economy) / n_economies,
                "observations": len(s),
                "first_year": int(s.index.get_level_values("year").min()),
                "last_year": int(s.index.get_level_values("year").max()),
                "median_years_per_economy": float(per_economy.median()),
                "economies_with_10plus_years": int((per_economy >= 10).sum()),
            }
        )
    return pd.DataFrame(rows)


def economies_per_year(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Number of economies reporting each series in each year (rows: year)."""
    return df[columns].notna().groupby(level="year").sum().astype(int)


def education_complete_count(df: pd.DataFrame, year: int) -> int:
    """Economies reporting all three education rates in ``year`` itself."""
    return int(df.dropna(subset=EDUCATION).groupby(level="year").size().get(year, 0))


def default_year(df: pd.DataFrame, share: float = 0.75) -> int:
    """Latest year in which the education series (the sparsest) cover at least ``share`` of their best year."""
    counts = economies_per_year(df, EDUCATION).min(axis=1)
    return int(counts[counts >= share * counts.max()].index.max())


def trend(df: pd.DataFrame, countries: list[str], column: str, start: int, end: int) -> pd.DataFrame:
    """Tidy (iso3, year, value) for one column, selected countries and a year window."""
    out = df[column].dropna().reset_index().rename(columns={column: "value"})
    out = out[out["iso3"].isin(countries) & out["year"].between(start, end)]
    return out.reset_index(drop=True)


def median_by_year(df: pd.DataFrame, column: str) -> pd.Series:
    """Median of ``column`` across economies, by year. A plain median: economies are not weighted by labour force."""
    return df[column].dropna().groupby(level="year").median()


def cross_section(df: pd.DataFrame, year: int, names: dict[str, str] | None = None) -> pd.DataFrame:
    """One row per economy for ``year`` with every column; economy names added if given."""
    out = df.xs(year, level="year").reset_index()
    if names is not None:
        out.insert(1, "country", out["iso3"].map(names))
    return out


def largest(frame: pd.DataFrame, column: str, n: int = 10, *, ascending: bool = False) -> pd.DataFrame:
    """The ``n`` rows with the largest (or, with ``ascending``, smallest) non-missing ``column``."""
    return frame.dropna(subset=[column]).sort_values(column, ascending=ascending).head(n).reset_index(drop=True)


def education_snapshot(df: pd.DataFrame, year: int, max_age: int = MAX_EDUCATION_AGE, names: dict[str, str] | None = None) -> pd.DataFrame:
    """Latest complete education record per economy within ``max_age`` years up to ``year``.

    Only economies with all three education rates in some year of ``[year - max_age, year]`` appear. The year that
    stands in for ``year`` is reported as ``year_used``. Columns: basic, intermediate, advanced, total, education_gap.
    """
    recent = df.loc[(slice(None), slice(year - max_age, year)), EDUCATION + ["total", "education_gap"]].dropna(subset=EDUCATION)
    if recent.empty:
        return pd.DataFrame(columns=["iso3", "year_used", *EDUCATION, "total", "education_gap"])
    latest = recent.reset_index().sort_values(["iso3", "year"]).groupby("iso3").tail(1).rename(columns={"year": "year_used"})
    if names is not None:
        latest.insert(1, "country", latest["iso3"].map(names))
    return latest.reset_index(drop=True)


def education_profile(df: pd.DataFrame, iso3: str, year: int, max_age: int = MAX_EDUCATION_AGE) -> tuple[int | None, pd.Series]:
    """Rates by education level (plus the all-ages total) for one country.

    Uses ``year`` if the country has any education rate then, otherwise the latest earlier year within ``max_age``.
    Returns ``(year_used, series)``; ``year_used`` is None and the series is empty when nothing is available.
    """
    if iso3 not in df.index.get_level_values("iso3"):
        return None, pd.Series(dtype=float)
    rows = df.loc[iso3].loc[year - max_age : year, EDUCATION + ["total"]].dropna(subset=EDUCATION, how="all")
    if rows.empty:
        return None, pd.Series(dtype=float)
    used = int(rows.index.max())
    return used, rows.loc[used]


def education_years(df: pd.DataFrame, iso3: str) -> list[int]:
    """Years in which a country reports at least one education-specific rate."""
    if iso3 not in df.index.get_level_values("iso3"):
        return []
    rows = df.loc[iso3, EDUCATION].dropna(how="all")
    return [int(y) for y in rows.index]


def gender_summary(df: pd.DataFrame, year: int) -> dict[str, float]:
    """Economies reporting, how many have higher female unemployment, and the median gap, for ``year``."""
    gap = df["gender_gap"].dropna().xs(year, level="year")
    return {
        "economies": int(len(gap)),
        "female_higher": int((gap > 0).sum()),
        "male_higher": int((gap < 0).sum()),
        "median_gap_pp": float(gap.median()),
    }


def main() -> None:
    names = wb.names()
    df = load()
    n = economy_count()
    print(f"World Bank economies: {n}")
    print("\nCoverage by series:")
    print(coverage_table(df, n).round(1).to_string(index=False))

    year = default_year(df)
    counts = economies_per_year(df, list(INDICATORS)).loc[[2000, 2010, 2019, year, 2025]]
    print(f"\nDefault comparison year (education series >= 75% of their best year): {year}")
    print("Economies reporting each series:")
    print(counts.to_string())
    headline = economies_per_year(df, ["total", "female", "male", "youth"]).loc[1991:]
    print(f"Headline series (total, female, male, youth): between {headline.min().min()} and {headline.max().max()} economies in every year {headline.index.min()}-{headline.index.max()}")
    print("Economies with all three education rates in the same year, by year (selected):")
    complete = df.dropna(subset=EDUCATION).groupby(level="year").size()
    print(complete.loc[[2000, 2010, 2019, year, 2025]].to_string())
    snap = education_snapshot(df, year, names=names)
    print(f"With the {MAX_EDUCATION_AGE}-year fallback, {len(snap)} economies have a complete education record for {year} "
          f"({(snap['year_used'] == year).sum()} in {year} itself)")

    print(f"\n--- Gender gap, {year} ---")
    g = gender_summary(df, year)
    print(g)
    cs = cross_section(df, year, names)
    cols = ["country", "female", "male", "gender_gap"]
    print("Largest female-higher gaps:")
    print(largest(cs, "gender_gap", 5)[cols].round(1).to_string(index=False))
    print("Largest male-higher gaps:")
    print(largest(cs, "gender_gap", 5, ascending=True)[cols].round(1).to_string(index=False))
    med = median_by_year(df, "gender_gap")
    print(f"Median gender gap: {med.loc[1991]:.2f} pp in 1991, {med.loc[2000]:.2f} in 2000, {med.loc[2019]:.2f} in 2019, {med.loc[year]:.2f} in {year}")

    print(f"\n--- Youth, {year} ---")
    ratio = cs["youth_ratio"].dropna()
    print(f"Median youth/all-ages ratio {ratio.median():.2f}; youth rate below the all-ages rate in {(ratio < 1).sum()} of {len(ratio)} economies")
    print(largest(cs, "youth_ratio", 5)[["country", "youth", "total", "youth_ratio"]].round(1).to_string(index=False))
    print(f"Median youth unemployment {cs['youth'].median():.1f}% vs median total {cs['total'].median():.1f}%")

    print(f"\n--- Education, {year} (record within {MAX_EDUCATION_AGE} years) ---")
    exact = education_snapshot(df, year, max_age=0)
    print(f"Advanced-education rate above basic-education rate in {(exact['education_gap'] < 0).sum()} of {len(exact)} economies in {year} itself, "
          f"and in {(snap['education_gap'] < 0).sum()} of {len(snap)} using the {MAX_EDUCATION_AGE}-year fallback; "
          f"median basic minus advanced = {snap['education_gap'].median():.2f} pp (fallback sample)")
    ecols = ["country", "year_used", "basic", "advanced", "education_gap"]
    print("Graduates worst off relative to basic education:")
    print(largest(snap, "education_gap", 5, ascending=True)[ecols].round(1).to_string(index=False))
    print("Basic education worst off relative to graduates:")
    print(largest(snap, "education_gap", 5)[ecols].round(1).to_string(index=False))
    for iso in ("USA", "GBR", "IND", "ZAF"):
        used, prof = education_profile(df, iso, year)
        print(f"{names[iso]} ({used}): " + ", ".join(f"{k} {v:.1f}" for k, v in prof.items()))

    total_med = median_by_year(df, "total")
    print(f"\nMedian total unemployment: {total_med.loc[2019]:.2f}% (2019), {total_med.loc[2020]:.2f}% (2020), {total_med.loc[year]:.2f}% ({year})")


if __name__ == "__main__":
    main()
