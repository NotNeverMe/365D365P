"""Government debt relative to GDP and to revenue.

Everything is computed from four World Bank central government series (all consistent in scope)
plus the long US history from FRED.

Derived ratios, with GDP cancelling out because every input is a percentage of the same GDP:

    debt_to_revenue     = debt (% GDP) / revenue excluding grants (% GDP)            [years of revenue]
    interest_gdp        = interest share of expense (%) / 100 x expense (% GDP)      [% GDP]
    interest_to_revenue = interest_gdp / revenue (% GDP) x 100                        [% of revenue]

Run ``python projects/011-national-debt-dashboard/national_debt.py`` for the numbers in the README.
"""

from __future__ import annotations

import pandas as pd

from core import fred
from core import worldbank as wb

INPUTS = {
    "debt": "GC.DOD.TOTL.GD.ZS",  # central government debt, % of GDP
    "revenue": "GC.REV.XGRT.GD.ZS",  # revenue excluding grants, % of GDP
    "interest_share": "GC.XPN.INTP.ZS",  # interest payments, % of expense
    "expense": "GC.XPN.TOTL.GD.ZS",  # expense, % of GDP
}
CROSS_CHECK = {"wb_interest_to_revenue": "GC.XPN.INTP.RV.ZS"}  # World Bank's own interest / revenue
FRED_GROSS = "GFDEGDQ188S"  # US federal debt, total public debt (gross), % of GDP, quarterly
FRED_PUBLIC = "FYGFGDQ188S"  # US federal debt held by the public, % of GDP, quarterly

# Inputs behind each derived measure, used to explain why a country is missing from a chart.
MEASURE_INPUTS = {
    "debt": ["debt"],
    "debt_to_revenue": ["debt", "revenue"],
    "interest_to_revenue": ["interest_share", "expense", "revenue"],
}

LABELS = {
    "debt": "Central government debt, % of GDP",
    "revenue": "Revenue excluding grants, % of GDP",
    "debt_to_revenue": "Debt-to-revenue, years of revenue",
    "interest_to_revenue": "Interest payments, % of revenue",
    "interest_gdp": "Interest payments, % of GDP",
}


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Append ``debt_to_revenue``, ``interest_gdp`` and ``interest_to_revenue`` (NaN where an input is missing).

    Non-positive revenue is treated as missing rather than producing infinities.
    """
    out = df.copy()
    revenue = out["revenue"].where(out["revenue"] > 0)
    out["debt_to_revenue"] = out["debt"] / revenue
    out["interest_gdp"] = out["interest_share"] / 100.0 * out["expense"]
    out["interest_to_revenue"] = out["interest_gdp"] / revenue * 100.0
    return out


def load(*, refresh: bool = False) -> pd.DataFrame:
    """Wide frame indexed by (iso3, year): the four inputs, the World Bank cross-check, and the derived ratios."""
    return add_ratios(wb.indicators({**INPUTS, **CROSS_CHECK}, refresh=refresh))


# ----------------------------------------------------------------------------- coverage


def coverage_by_year(df: pd.DataFrame) -> pd.DataFrame:
    """Number of countries (and share of all economies) with each measure available, per year."""
    n_economies = len(wb.names())
    columns = ["debt", "revenue", "debt_to_revenue", "interest_to_revenue"]
    counts = df[columns].notna().groupby(level="year").sum().astype(int)
    for col in columns:
        counts[f"{col}_share"] = counts[col] / n_economies
    return counts


def coverage_by_country(df: pd.DataFrame, first_year: int = 1990) -> pd.DataFrame:
    """One row per country that reports any input: first/last year of debt data and years available since ``first_year``.

    No country is dropped: those with no debt figure at all appear with empty first/last years.
    """
    years = df.index.get_level_values("year")
    measures = {"debt": "debt_years", "debt_to_revenue": "debt_to_revenue_years", "interest_to_revenue": "interest_to_revenue_years"}
    counts = df.loc[years >= first_year, list(measures)].notna().groupby(level="iso3").sum().rename(columns=measures)
    spans = df["debt"].dropna().reset_index().groupby("iso3")["year"].agg(debt_first_year="min", debt_last_year="max")
    universe = df.index[df[list(INPUTS)].notna().any(axis=1)].get_level_values("iso3").unique()
    out = counts.reindex(universe).fillna(0).astype(int).join(spans).reset_index()
    out["country"] = out["iso3"].map(wb.names()).fillna(out["iso3"])
    out["possible_years"] = int(years.max()) - first_year + 1
    columns = ["iso3", "country", "debt_first_year", "debt_last_year", *measures.values(), "possible_years"]
    return out[columns].sort_values(["debt_to_revenue_years", "country"], ascending=[False, True]).reset_index(drop=True)


def broad_year(df: pd.DataFrame, column: str = "debt_to_revenue", min_share_of_peak: float = 0.75) -> int:
    """Latest year in which ``column`` is reported by at least ``min_share_of_peak`` of its best-covered year's countries.

    Coverage of these series is patchy and the newest years are thin, so "latest year" would mislead.
    """
    per_year = df[column].dropna().groupby(level="year").size()
    eligible = per_year[per_year >= min_share_of_peak * per_year.max()]
    return int(eligible.index.max())


# ------------------------------------------------------------------------ cross sections


def latest_complete(df: pd.DataFrame, columns: list[str], year: int, max_lag: int = 0) -> pd.DataFrame:
    """For each country, the latest year in ``[year - max_lag, year]`` where every ``columns`` entry is present.

    Returns one row per country with ``iso3, country, obs_year`` and the requested columns, all taken from
    the same year (a ratio is never built from inputs of different years).
    """
    years = df.index.get_level_values("year")
    window = df[(years <= year) & (years >= year - max_lag)].dropna(subset=columns)
    window = window.reset_index().sort_values(["iso3", "year"]).groupby("iso3").tail(1)
    window = window.rename(columns={"year": "obs_year"})
    window["country"] = window["iso3"].map(wb.names())
    return window[["iso3", "country", "obs_year", *columns]].reset_index(drop=True)


def excluded_countries(df: pd.DataFrame, measure: str, year: int, max_lag: int = 0) -> pd.DataFrame:
    """Countries that report some input at some point but are absent from ``measure`` in the window, and why.

    Columns: iso3, country, has_in_window (inputs observed somewhere in the window), missing_in_window.
    """
    inputs = MEASURE_INPUTS[measure]
    included = set(latest_complete(df, [measure], year, max_lag)["iso3"])
    universe = set(df.index[df[list(INPUTS)].notna().any(axis=1)].get_level_values("iso3"))
    years = df.index.get_level_values("year")
    seen = df.loc[(years <= year) & (years >= year - max_lag), inputs].notna().groupby(level="iso3").any()
    rows = []
    for iso3 in sorted(universe - included):
        have = seen.loc[iso3] if iso3 in seen.index else pd.Series(False, index=inputs)
        rows.append(
            {
                "iso3": iso3,
                "country": wb.names().get(iso3, iso3),
                "has_in_window": ", ".join(have[have].index) or "nothing",
                "missing_in_window": ", ".join(have[~have].index) or "no single year with all inputs",
            }
        )
    return pd.DataFrame(rows, columns=["iso3", "country", "has_in_window", "missing_in_window"])


def trajectories(df: pd.DataFrame, iso3s: list[str], column: str, first: int, last: int) -> pd.DataFrame:
    """Tidy (iso3, country, year, value) for line charts."""
    sub = df.loc[df.index.get_level_values("iso3").isin(iso3s), [column]].dropna().reset_index()
    sub = sub[(sub["year"] >= first) & (sub["year"] <= last)].rename(columns={column: "value"})
    sub["country"] = sub["iso3"].map(wb.names())
    return sub.sort_values(["iso3", "year"]).reset_index(drop=True)


def rank_comparison(df: pd.DataFrame, year: int, max_lag: int = 0) -> pd.DataFrame:
    """Debt-to-GDP against debt-to-revenue for countries that have both, with each ranking (1 = highest).

    ``rank_shift`` is ``rank_debt_gdp - rank_debt_revenue``: positive means the country looks worse once
    revenue, not GDP, is the yardstick.
    """
    out = latest_complete(df, ["debt", "revenue", "debt_to_revenue"], year, max_lag).rename(columns={"debt": "debt_gdp", "revenue": "revenue_gdp"})
    out["rank_debt_gdp"] = out["debt_gdp"].rank(ascending=False, method="min").astype(int)
    out["rank_debt_revenue"] = out["debt_to_revenue"].rank(ascending=False, method="min").astype(int)
    out["rank_shift"] = out["rank_debt_gdp"] - out["rank_debt_revenue"]
    groups = wb.countries().set_index("iso3")["income_group"]
    out["income_group"] = out["iso3"].map(groups)
    return out.sort_values("debt_gdp", ascending=False).reset_index(drop=True)


def rank_correlation(ranks: pd.DataFrame) -> float:
    """Spearman correlation between the debt-to-GDP and debt-to-revenue orderings."""
    return float(ranks["debt_gdp"].corr(ranks["debt_to_revenue"], method="spearman"))


def interest_burden(df: pd.DataFrame, year: int, top: int = 15, max_lag: int = 0) -> pd.DataFrame:
    """Countries ranked by interest payments as a share of revenue, with the components shown."""
    cols = ["interest_to_revenue", "interest_share", "expense", "revenue", "interest_gdp"]
    out = latest_complete(df, cols, year, max_lag)
    return out.sort_values("interest_to_revenue", ascending=False).head(top).reset_index(drop=True)


def formula_check(df: pd.DataFrame, tolerance: float = 1.0) -> dict[str, float]:
    """Compare the derived interest-to-revenue with the World Bank's own GC.XPN.INTP.RV.ZS series.

    ``share_derived_higher_when_off`` is, among country-years more than ``tolerance`` points apart,
    the share where the derived figure is the larger one (a larger World Bank denominator would do that).
    """
    both = df[["interest_to_revenue", "wb_interest_to_revenue"]].dropna()
    signed = both["interest_to_revenue"] - both["wb_interest_to_revenue"]
    off = signed[signed.abs() > tolerance]
    return {
        "n": float(len(both)),
        "share_within_tolerance": float((signed.abs() <= tolerance).mean()),
        "median_abs_gap": float(signed.abs().median()),
        "correlation": float(both.corr().iloc[0, 1]),
        "n_off": float(len(off)),
        "share_derived_higher_when_off": float((off > 0).mean()) if len(off) else float("nan"),
    }


# --------------------------------------------------------------------------- US from FRED


def us_history(*, refresh: bool = False) -> pd.DataFrame:
    """Quarterly US federal debt, % of GDP: ``gross`` (total public debt) and ``held_by_public``."""
    return fred.frame({"gross": FRED_GROSS, "held_by_public": FRED_PUBLIC}, refresh=refresh)


def us_extremes(series: pd.Series) -> dict[str, tuple[str, float]]:
    """Date (as ``YYYY-Qn``) and value of the minimum, maximum and latest observation."""

    def label(ts: pd.Timestamp) -> str:
        return f"{ts.year}-Q{(ts.month - 1) // 3 + 1}"

    s = series.dropna()
    return {
        "min": (label(s.idxmin()), float(s.min())),
        "max": (label(s.idxmax()), float(s.max())),
        "latest": (label(s.index[-1]), float(s.iloc[-1])),
    }


def us_world_bank_comparison(df: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Annual average of the FRED series next to the World Bank US central government debt figure."""
    annual = history.groupby(history.index.year).mean()
    us = df["debt"].xs("USA", level="iso3").rename("world_bank")
    return pd.concat([us, annual], axis=1).dropna(subset=["world_bank"]).rename_axis("year")


# ------------------------------------------------------------------------------------ summary


def main() -> None:
    df = load()
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 20)
    fmt = lambda v: f"{v:.1f}"  # noqa: E731

    cov = coverage_by_year(df)
    n_ever = int(df["debt"].dropna().index.get_level_values("iso3").nunique())
    print(f"== Coverage == economies with any central government debt figure: {n_ever} of {len(wb.names())}")
    print(cov.loc[[1995, 2000, 2010, 2015, 2019, 2020, 2021, 2022, 2023, 2024], ["debt", "revenue", "debt_to_revenue", "interest_to_revenue"]].to_string())
    by_country = coverage_by_country(df)
    for iso in ["USA", "GBR", "JPN", "FRA", "DEU", "ITA", "CHN", "GRC", "ARG"]:
        row = by_country[by_country["iso3"] == iso]
        text = "no debt figure in any year" if row.empty or pd.isna(row["debt_first_year"].iloc[0]) else (
            f"debt {int(row['debt_first_year'].iloc[0])}-{int(row['debt_last_year'].iloc[0])}, {int(row['debt_years'].iloc[0])} years since 1990")
        print(f"  {wb.names()[iso]:16s} {text}")

    year = broad_year(df)
    ranks = rank_comparison(df, year)
    print(f"\n== Debt-to-GDP vs debt-to-revenue, {year} ({len(ranks)} countries) ==")
    print(f"Spearman correlation of the two orderings: {rank_correlation(ranks):.2f}")
    show = ["country", "debt_gdp", "revenue_gdp", "debt_to_revenue", "rank_debt_gdp", "rank_debt_revenue"]
    print("Highest debt-to-GDP:")
    print(ranks.head(6)[show].to_string(index=False, float_format=fmt))
    print("Highest debt-to-revenue:")
    print(ranks.sort_values("debt_to_revenue", ascending=False).head(6)[show].to_string(index=False, float_format=fmt))
    print("Biggest moves up (look worse on revenue):")
    print(ranks.sort_values("rank_shift", ascending=False).head(4)[show + ["rank_shift"]].to_string(index=False, float_format=fmt))
    print("Biggest moves down (look better on revenue):")
    print(ranks.sort_values("rank_shift").head(4)[show + ["rank_shift"]].to_string(index=False, float_format=fmt))

    iyear = broad_year(df, "interest_to_revenue")
    burden = interest_burden(df, iyear, top=8)
    n_int = len(latest_complete(df, ["interest_to_revenue"], iyear))
    all_int = latest_complete(df, ["interest_to_revenue"], iyear)["interest_to_revenue"]
    print(f"\n== Interest as % of revenue, {iyear} ({n_int} countries, median {all_int.median():.1f}%) ==")
    print(burden[["country", "interest_to_revenue", "interest_share", "expense", "revenue"]].to_string(index=False, float_format=fmt))

    check = formula_check(df)
    print(f"\n== Formula check vs World Bank GC.XPN.INTP.RV.ZS == n={check['n']:.0f}, within 1 point: {check['share_within_tolerance']:.1%}, "
          f"median gap {check['median_abs_gap']:.2f} points, correlation {check['correlation']:.3f}; "
          f"{check['n_off']:.0f} country-years differ by more than 1 point, derived figure is the higher one in {check['share_derived_higher_when_off']:.1%}")

    hist = us_history()
    print("\n== US federal debt, % of GDP (FRED, quarterly) ==")
    for col in hist:
        ex = us_extremes(hist[col])
        print(f"{col:15s} min {ex['min'][1]:.1f} ({ex['min'][0]}), max {ex['max'][1]:.1f} ({ex['max'][0]}), latest {ex['latest'][1]:.1f} ({ex['latest'][0]}); "
              f"starts {hist[col].dropna().index.min().date()}")
    cmp = us_world_bank_comparison(df, hist)
    print("World Bank US central government debt vs FRED annual averages:")
    print(cmp.loc[[1995, 2000, 2010, 2020, 2022]].to_string(float_format=fmt))


if __name__ == "__main__":
    main()
