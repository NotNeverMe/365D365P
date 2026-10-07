"""US CPI inflation by category, plus headline inflation across countries.

US data come from FRED (``core.fred``), not-seasonally-adjusted CPI-U indexes, so that the 12-month change
equals the headline rate the BLS publishes. Cross-country data are World Bank ``FP.CPI.TOTL.ZG``.

Category weights
----------------
The BLS relative-importance table (the official weights) could not be downloaded: bls.gov answered HTTP 403
"Access Denied" from this environment, and that was respected rather than bypassed. The weights here are therefore
**estimated from the indexes themselves**: for each base month, a non-negative least-squares regression of the
monthly log change of the all-items index on the monthly log changes of its categories, over the latest 60 months.
The contribution of category ``i`` to the 12-month change in month ``t`` is then::

    contribution_i(t) = estimated_weight_i(t - 12 months) x yoy_i(t)        (percentage points)

Whatever the weights do not explain is reported as ``Residual`` so the stack always adds to the headline rate.

Each breakdown is a partition of the all-items index, so categories never overlap and double count.

Run ``python projects/002-inflation-tracker/inflation_tracker.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from core import fred
from core import worldbank as wb

HEADLINE = "All items"
HEADLINE_ID = "CPIAUCNS"
RESIDUAL = "Residual"

BREAKDOWNS: dict[str, dict[str, str]] = {
    "Eight major groups": {
        "Food and beverages": "CPIFABNS",
        "Housing": "CPIHOSNS",
        "Apparel": "CPIAPPNS",
        "Transportation": "CPITRNNS",
        "Medical care": "CPIMEDNS",
        "Recreation": "CPIRECNS",
        "Education and communication": "CPIEDUNS",
        "Other goods and services": "CPIOGSNS",
    },
    "Housing split out (shelter separate)": {
        "Food and beverages": "CPIFABNS",
        "Shelter": "CUUR0000SAH1",
        "Fuels and utilities": "CUUR0000SAH2",
        "Household furnishings and operations": "CUUR0000SAH3",
        "Apparel": "CPIAPPNS",
        "Transportation": "CPITRNNS",
        "Medical care": "CPIMEDNS",
        "Recreation": "CPIRECNS",
        "Education and communication": "CPIEDUNS",
        "Other goods and services": "CPIOGSNS",
    },
    "Food, energy, core goods, core services": {
        "Food": "CPIUFDNS",
        "Energy": "CPIENGNS",
        "Core goods": "CUUR0000SACL1E",
        "Core services": "CUUR0000SASLE",
    },
}

SERIES_NAMES = {
    HEADLINE_ID: "All items",
    "CPIFABNS": "Food and beverages",
    "CPIHOSNS": "Housing",
    "CPIAPPNS": "Apparel",
    "CPITRNNS": "Transportation",
    "CPIMEDNS": "Medical care",
    "CPIRECNS": "Recreation",
    "CPIEDUNS": "Education and communication",
    "CPIOGSNS": "Other goods and services",
    "CUUR0000SAH1": "Shelter",
    "CUUR0000SAH2": "Fuels and utilities",
    "CUUR0000SAH3": "Household furnishings and operations",
    "CPIUFDNS": "Food",
    "CPIENGNS": "Energy",
    "CUUR0000SACL1E": "Commodities less food and energy commodities (core goods)",
    "CUUR0000SASLE": "Services less energy services (core services)",
}

FIRST_MONTH = pd.Timestamp("1993-01-01")  # first month in which every series used here exists
WINDOW = 60  # monthly changes used for each weight estimate
MIN_OBS = 48  # fewest monthly changes needed before a weight is reported
WB_INFLATION = "FP.CPI.TOTL.ZG"


# ---------------------------------------------------------------------------------------------- US CPI


def series_catalog() -> pd.DataFrame:
    """Every FRED series used: id, name, first and last month, observations, and months missing since ``FIRST_MONTH``."""
    data = {sid: fred.series(sid) for sid in SERIES_NAMES}
    rows = []
    for sid, s in data.items():
        expected = pd.date_range(FIRST_MONTH, s.index.max(), freq="MS")
        rows.append(
            {
                "series_id": sid,
                "name": SERIES_NAMES[sid],
                "first": s.index.min().strftime("%Y-%m"),
                "last": s.index.max().strftime("%Y-%m"),
                "observations": len(s),
                f"missing_since_{FIRST_MONTH:%Y-%m}": ", ".join(d.strftime("%Y-%m") for d in expected.difference(s.index)),
            }
        )
    return pd.DataFrame(rows)


def load_levels(breakdown: str) -> pd.DataFrame:
    """Monthly CPI index levels from ``FIRST_MONTH``: ``All items`` then each category, on a gap-free monthly index.

    Months the BLS did not publish (October 2025) stay as NaN rather than being filled, so that 12-month
    changes always compare the same calendar month. All breakdowns share the same start month so they are comparable.
    """
    cols = {HEADLINE: HEADLINE_ID, **BREAKDOWNS[breakdown]}
    raw = pd.concat({name: fred.series(sid) for name, sid in cols.items()}, axis=1)
    return raw.loc[FIRST_MONTH:].reindex(pd.date_range(FIRST_MONTH, raw.index.max(), freq="MS"))


def categories(levels: pd.DataFrame) -> list[str]:
    return [c for c in levels.columns if c != HEADLINE]


def yoy(levels: pd.DataFrame) -> pd.DataFrame:
    """12-month percentage change. ``levels`` must have a gap-free monthly index (see ``load_levels``)."""
    return levels.pct_change(12, fill_method=None) * 100


def nnls_weights(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Non-negative least-squares coefficients of ``y`` on the columns of ``x`` (no intercept)."""
    coef, _ = nnls(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    return coef


def estimate_weights(levels: pd.DataFrame, window: int = WINDOW, min_obs: int = MIN_OBS) -> pd.DataFrame:
    """Estimated category weights for each month, from the latest ``window`` monthly changes up to that month.

    Rows are months, columns are categories, and values are fractions of the all-items index (they should sum
    to roughly one). Months with fewer than ``min_obs`` usable monthly changes behind them are NaN.
    """
    cats = categories(levels)
    changes = np.log(levels).diff().dropna()
    out = pd.DataFrame(np.nan, index=levels.index, columns=cats)
    for month in levels.index:
        win = changes.loc[:month].tail(window)
        if len(win) >= min_obs:
            out.loc[month] = nnls_weights(win[HEADLINE].to_numpy(), win[cats].to_numpy())
    return out


def contributions(levels: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Percentage-point contribution of each category to the 12-month all-items rate, plus ``Residual``.

    The weights used for month ``t`` are those estimated at ``t - 12`` months (the base month of the comparison).
    """
    cats = categories(levels)
    rates = yoy(levels)
    base_weights = weights.reindex(levels.index).shift(12)
    parts = base_weights[cats] * rates[cats]
    parts[RESIDUAL] = rates[HEADLINE] - parts[cats].sum(axis=1, skipna=False)
    return parts.dropna()


def month_table(levels: pd.DataFrame, weights: pd.DataFrame, month: pd.Timestamp) -> pd.DataFrame:
    """For one month: base weight, 12-month rate, contribution and share of the headline, largest contributor first."""
    month = pd.Timestamp(month)
    cats = categories(levels)
    parts = contributions(levels, weights).loc[month]
    base = month - pd.DateOffset(months=12)
    headline = yoy(levels).loc[month, HEADLINE]
    table = pd.DataFrame(
        {
            "category": cats,
            "weight_pct": (weights.loc[base, cats] * 100).to_numpy(),
            "yoy_pct": yoy(levels).loc[month, cats].to_numpy(),
            "contribution_pp": parts[cats].to_numpy(),
        }
    )
    table["share_of_headline_pct"] = table["contribution_pp"] / headline * 100 if headline else np.nan
    table = table.sort_values("contribution_pp", ascending=False).reset_index(drop=True)
    residual = pd.DataFrame([{"category": RESIDUAL, "contribution_pp": parts[RESIDUAL]}])
    residual["share_of_headline_pct"] = residual["contribution_pp"] / headline * 100 if headline else np.nan
    return pd.concat([table, residual], ignore_index=True)


def fit_summary(parts: pd.DataFrame, weights: pd.DataFrame) -> dict[str, float]:
    """How well the estimated weights reproduce the headline: residual size and the sum of the weights."""
    resid = parts[RESIDUAL].abs()
    estimated = weights.dropna()
    sums = estimated.sum(axis=1)
    return {
        "months": len(parts),
        "mean_abs_residual_pp": float(resid.mean()),
        "max_abs_residual_pp": float(resid.max()),
        "weight_sum_min": float(sums.min()),
        "weight_sum_max": float(sums.max()),
        "share_months_with_a_zero_weight": float((estimated < 1e-9).any(axis=1).mean()),
    }


# ----------------------------------------------------------------------------------- cross-country


def load_world_inflation() -> pd.DataFrame:
    """World Bank consumer-price inflation (annual %), a (year x iso3) frame for real economies only."""
    wide = wb.indicators({"inflation": WB_INFLATION})["inflation"].unstack("iso3")
    return wide.sort_index()


def country_summary(wide: pd.DataFrame, countries: list[str], start: int, end: int, names: dict[str, str] | None = None) -> pd.DataFrame:
    """Average, median, peak and latest annual inflation for each country in ``start``..``end``."""
    window = wide.loc[start:end].reindex(columns=countries)
    rows = []
    for iso in countries:
        s = window[iso].dropna()
        rows.append(
            {
                "country": (names or {}).get(iso, iso),
                "iso3": iso,
                "mean_pct": s.mean() if len(s) else np.nan,
                "median_pct": s.median() if len(s) else np.nan,
                "peak_pct": s.max() if len(s) else np.nan,
                "peak_year": int(s.idxmax()) if len(s) else np.nan,
                "latest_pct": s.iloc[-1] if len(s) else np.nan,
                "latest_year": int(s.index[-1]) if len(s) else np.nan,
                "years_with_data": len(s),
                "years_expected": end - start + 1,
            }
        )
    return pd.DataFrame(rows)


def count_above(wide: pd.DataFrame, year: int, threshold: float) -> tuple[int, int]:
    """(economies with inflation above ``threshold`` %, economies reporting) in ``year``."""
    row = wide.loc[year].dropna()
    return int((row > threshold).sum()), int(len(row))


def world_coverage(wide: pd.DataFrame) -> dict[str, int]:
    counts = wide.notna().sum(axis=1)
    return {
        "economies": int(wide.notna().any().sum()),
        "first_year": int(counts[counts > 0].index.min()),
        "last_year": int(counts[counts > 0].index.max()),
        "economies_in_last_year": int(counts[counts > 0].iloc[-1]),
    }


def annual_average_inflation(levels: pd.Series) -> pd.Series:
    """Calendar-year average index over the previous year's, in %. Years with any missing month are dropped."""
    grouped = levels.groupby(levels.index.year)
    mean = grouped.mean().where(grouped.count() == 12)
    return (mean / mean.shift(1) - 1) * 100


def main() -> None:
    catalog = series_catalog()
    print("FRED series used (all load):")
    print(catalog.to_string(index=False))

    for name in BREAKDOWNS:
        levels = load_levels(name)
        weights = estimate_weights(levels)
        parts = contributions(levels, weights)
        fit = fit_summary(parts, weights)
        latest = parts.index.max()
        print(f"\n=== {name} ===")
        print(f"levels {levels.index.min():%Y-%m} to {levels.index.max():%Y-%m}; contributions for {parts.index.min():%Y-%m} to {latest:%Y-%m} ({fit['months']} months)")
        print(
            f"fit: mean |residual| {fit['mean_abs_residual_pp']:.3f} pp, max {fit['max_abs_residual_pp']:.2f} pp; "
            f"unconstrained weights sum to {fit['weight_sum_min']:.3f} to {fit['weight_sum_max']:.3f}; "
            f"a weight is pinned at zero in {fit['share_months_with_a_zero_weight']:.1%} of months"
        )
        pinned = (weights.dropna() < 1e-9).mean().sort_values(ascending=False)
        print(f"most often pinned at zero: {pinned.index[0]} ({pinned.iloc[0]:.1%} of months)")
        head = yoy(levels)[HEADLINE]
        peak = head.loc[parts.index].idxmax()
        for label, month in (("Latest", latest), ("Peak", peak)):
            print(f"{label}: {month:%Y-%m}, headline {head[month]:.2f}%")
            print(month_table(levels, weights, month).round(2).to_string(index=False))
        print(f"Latest estimated weights (%), base month {latest - pd.DateOffset(months=12):%Y-%m}:")
        print((weights.loc[latest - pd.DateOffset(months=12)] * 100).round(1).to_string())

    levels = load_levels("Eight major groups")
    wb_wide = load_world_inflation()
    fred_annual = annual_average_inflation(levels[HEADLINE])
    us = wb_wide["USA"].dropna()
    common = fred_annual.dropna().index.intersection(us.index)
    diff = (fred_annual[common] - us[common]).abs()
    print(f"\nFRED annual-average CPI inflation vs World Bank FP.CPI.TOTL.ZG for the US, {common.min()}-{common.max()}: "
          f"max |difference| {diff.max():.4f} pp")
    cov = world_coverage(wb_wide)
    print(f"World Bank inflation coverage: {cov}")
    names = wb.names()
    for year in (2022, 2024):
        above, total = count_above(wb_wide, year, 10)
        print(f"{year}: {above} of {total} economies above 10% inflation")
    row = wb_wide.loc[2022].dropna().sort_values(ascending=False)
    print("Highest 2022:", ", ".join(f"{names.get(i, i)} {v:.0f}%" for i, v in row.head(4).items()))
    for iso in ("USA", "GBR", "DEU", "JPN", "TUR", "ARG"):
        print(f"  {names[iso]} 2022: {wb_wide.loc[2022, iso]:.1f}%")


if __name__ == "__main__":
    main()
