"""Living standards across countries: income, health, and how the world distribution of income has changed.

Four analyses on World Bank data:

* the **Preston curve**: life expectancy against log income per head, fitted by OLS each year;
* a **country comparison** table of income and related indicators;
* **absolute beta-convergence**: do poorer countries grow faster? ``growth_i = a + b * ln(income_i,start)``;
* the **population-weighted Gini** of the cross-country distribution of GDP per capita, a measure of
  between-country inequality (each person is assigned their country's average income).

Run ``python projects/012-gdp-per-capita-explorer/gdp_per_capita.py`` for the numbers quoted in the README.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

from core import worldbank as wb
from core.inequality import gini

SERIES = {
    "ppp": ("NY.GDP.PCAP.PP.KD", "GDP per capita, PPP (constant 2021 intl $)"),
    "nominal": ("NY.GDP.PCAP.CD", "GDP per capita (current US$)"),
    "life_exp": ("SP.DYN.LE00.IN", "Life expectancy at birth (years)"),
    "infant_mort": ("SP.DYN.IMRT.IN", "Infant mortality (per 1,000 live births)"),
    "pop": ("SP.POP.TOTL", "Population"),
    "co2_pc": ("EN.GHG.CO2.PC.CE.AR5", "CO2 emissions excl. LULUCF (t CO2e per person)"),
    "electricity": ("EG.USE.ELEC.KH.PC", "Electric power consumption (kWh per person)"),
}
LABELS = {key: label for key, (_, label) in SERIES.items()}
TABLE_COLUMNS = ["ppp", "nominal", "life_exp", "infant_mort", "pop", "co2_pc", "electricity"]


def load(*, refresh: bool = False) -> pd.DataFrame:
    """Wide frame indexed by (iso3, year), one column per entry in ``SERIES``. Economies only."""
    return wb.indicators({key: code for key, (code, _) in SERIES.items()}, refresh=refresh)


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per series: first/last year, countries ever covered, and the year with the widest coverage."""
    rows = []
    for key, label in LABELS.items():
        col = df[key].dropna()
        per_year = col.groupby(level="year").size()
        has_data = len(col) > 0
        rows.append(
            {
                "series": label,
                "first_year": int(per_year.index.min()) if has_data else None,
                "last_year": int(per_year.index.max()) if has_data else None,
                "countries": int(col.index.get_level_values("iso3").nunique()),
                "best_year": int(per_year.idxmax()) if has_data else None,
                "countries_in_best_year": int(per_year.max()) if has_data else 0,
            }
        )
    return pd.DataFrame(rows)


def latest_common_year(df: pd.DataFrame, columns: list[str], min_share_of_peak: float = 0.95) -> int:
    """Latest year in which every column in ``columns`` reaches ``min_share_of_peak`` of its own peak country count.

    The newest World Bank years are often thin, so "latest year" can mean a handful of countries.
    """
    ok = None
    for col in columns:
        per_year = df[col].dropna().groupby(level="year").size()
        good = set(per_year.index[per_year >= min_share_of_peak * per_year.max()])
        ok = good if ok is None else ok & good
    if not ok:
        raise ValueError(f"no year has broad coverage of {columns}")
    return int(max(ok))


# ---------------------------------------------------------------------------- regression


@dataclass(frozen=True)
class Regression:
    """Summary of one OLS/WLS fit with heteroskedasticity-robust (HC1) standard errors."""

    names: tuple[str, ...]
    params: tuple[float, ...]
    bse: tuple[float, ...]
    pvalues: tuple[float, ...]
    r2: float
    n: int

    def coef(self, name: str) -> float:
        return self.params[self.names.index(name)]

    def se(self, name: str) -> float:
        return self.bse[self.names.index(name)]

    def p(self, name: str) -> float:
        return self.pvalues[self.names.index(name)]


def _regress(y: pd.Series, x: pd.DataFrame, weights: pd.Series | None = None) -> Regression:
    if len(y) < x.shape[1] + 3:
        raise ValueError(f"too few observations ({len(y)}) for this regression")
    design = sm.add_constant(x, has_constant="add")
    model = sm.WLS(y, design, weights=weights) if weights is not None else sm.OLS(y, design)
    res = model.fit(cov_type="HC1")
    return Regression(
        names=tuple(design.columns),
        params=tuple(float(v) for v in res.params),
        bse=tuple(float(v) for v in res.bse),
        pvalues=tuple(float(v) for v in res.pvalues),
        r2=float(res.rsquared),
        n=int(res.nobs),
    )


# ------------------------------------------------------------------------- Preston curve


def preston_frame(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Countries with income, life expectancy and population in ``year`` (iso3, country, region, ppp, life_exp, pop)."""
    sub = df.xs(year, level="year")[["ppp", "life_exp", "pop"]].dropna().reset_index()
    meta = wb.countries().set_index("iso3")
    sub["country"] = sub["iso3"].map(wb.names())
    sub["region"] = sub["iso3"].map(meta["region"])
    return sub[["iso3", "country", "region", "ppp", "life_exp", "pop"]]


def fit_preston(df: pd.DataFrame, year: int, curvature: bool = False) -> Regression:
    """OLS of life expectancy on ln(GDP per capita, PPP) across countries in ``year``.

    With ``curvature`` the square of ln(income) is added. Each country counts once (not weighted by population).
    """
    sub = preston_frame(df, year)
    x = pd.DataFrame({"ln_income": np.log(sub["ppp"])})
    if curvature:
        x["ln_income_sq"] = x["ln_income"] ** 2
    return _regress(sub["life_exp"], x)


def preston_curve(fit: Regression, incomes) -> np.ndarray:
    """Life expectancy predicted by ``fit`` at the given incomes (PPP dollars)."""
    ln = np.log(np.asarray(incomes, dtype=float))
    y = fit.coef("const") + fit.coef("ln_income") * ln
    if "ln_income_sq" in fit.names:
        y = y + fit.coef("ln_income_sq") * ln**2
    return y


def preston_over_time(df: pd.DataFrame, first: int, last: int) -> pd.DataFrame:
    """Log-linear Preston fit for every year: intercept, slope, slope standard error, R-squared and n."""
    rows = []
    for year in range(first, last + 1):
        try:
            fit = fit_preston(df, year)
        except (KeyError, ValueError):
            continue
        rows.append(
            {
                "year": year,
                "intercept": fit.coef("const"),
                "slope": fit.coef("ln_income"),
                "slope_se": fit.se("ln_income"),
                "r2": fit.r2,
                "n": fit.n,
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ comparison table


def comparison_table(df: pd.DataFrame, iso3s: list[str], year: int) -> pd.DataFrame:
    """One row per requested country with each indicator for ``year``; gaps stay as NaN (nothing is filled in)."""
    values = df.xs(year, level="year")[TABLE_COLUMNS].reindex(iso3s)
    meta = wb.countries().set_index("iso3")
    out = values.copy()
    out.insert(0, "region", [meta["region"].get(c, "") for c in out.index])
    out.insert(0, "country", [wb.names().get(c, c) for c in out.index])
    return out.reset_index().rename(columns={"index": "iso3"})


# ------------------------------------------------------------------------- convergence


def beta_convergence(
    df: pd.DataFrame, start: int, end: int, min_population: float = 0.0, weighted: bool = False
) -> tuple[Regression, pd.DataFrame]:
    """Absolute beta-convergence over ``[start, end]``.

    Regresses average annual log growth of GDP per capita (PPP), in per cent per year,
    on ln(income in ``start``). The sample holds countries with income in both years and
    population (in ``start``) of at least ``min_population``. ``weighted`` weights by that
    population. Returns the regression of ``growth`` on ``ln_initial`` and the sample.

    A negative slope means poorer countries grew faster (convergence); a positive slope means
    richer countries grew faster (divergence).
    """
    if end <= start:
        raise ValueError("end must be after start")
    first = df.xs(start, level="year")
    last = df.xs(end, level="year")
    sample = pd.DataFrame({"initial_income": first["ppp"], "final_income": last["ppp"], "population": first["pop"]}).dropna()
    sample = sample[sample["population"] >= min_population]
    sample["ln_initial"] = np.log(sample["initial_income"])
    sample["growth"] = np.log(sample["final_income"] / sample["initial_income"]) / (end - start) * 100.0
    reg = _regress(sample["growth"], sample[["ln_initial"]], sample["population"] if weighted else None)
    sample = sample.reset_index()
    sample["country"] = sample["iso3"].map(wb.names())
    sample["region"] = sample["iso3"].map(wb.countries().set_index("iso3")["region"])
    return reg, sample


def convergence_speed(beta_pct: float, years: int) -> tuple[float, float] | None:
    """Annual convergence rate and half-life (years) implied by a beta in percentage points per log point.

    Uses ``b = -(1 - exp(-lambda * T)) / T`` (Barro and Sala-i-Martin), so
    ``lambda = -ln(1 + b * T) / T``. Returns ``None`` when ``beta`` is not negative (no convergence to describe).
    """
    b = beta_pct / 100.0
    if b >= 0 or 1.0 + b * years <= 0:
        return None
    rate = -math.log(1.0 + b * years) / years
    return rate, math.log(2.0) / rate


def convergence_by_window(df: pd.DataFrame, windows: list[tuple[int, int]], min_population: float = 0.0, weighted: bool = False) -> pd.DataFrame:
    """Beta, standard error, p-value and sample size for each ``(start, end)`` window."""
    rows = []
    for start, end in windows:
        reg, _ = beta_convergence(df, start, end, min_population, weighted)
        rows.append(
            {
                "window": f"{start}-{end}",
                "beta": reg.coef("ln_initial"),
                "se": reg.se("ln_initial"),
                "p_value": reg.p("ln_initial"),
                "r2": reg.r2,
                "n": reg.n,
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------- inequality


def weighted_gini_by_year(df: pd.DataFrame, exclude: tuple[str, ...] | list[str] = ()) -> pd.DataFrame:
    """Gini of the cross-country distribution of GDP per capita (PPP), per year.

    ``gini_weighted`` weights each country by its population, so it measures inequality between
    *people* of different countries' average incomes. ``gini_unweighted`` treats every country as
    one observation. ``pop_share_covered`` is the share of the population of (non-excluded) economies
    that has an income figure that year. Countries in ``exclude`` are left out of everything.
    """
    drop = set(exclude)
    keep = ~df.index.get_level_values("iso3").isin(drop)
    pop_total = df.loc[keep, "pop"].dropna().groupby(level="year").sum()
    both = df.loc[keep, ["ppp", "pop"]].dropna()
    rows = []
    for year, sub in both.groupby(level="year"):
        rows.append(
            {
                "year": int(year),
                "gini_weighted": gini(sub["ppp"], sub["pop"]),
                "gini_unweighted": gini(sub["ppp"]),
                "n": len(sub),
                "pop_share_covered": float(sub["pop"].sum() / pop_total.loc[year]),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------ summary


def main() -> None:
    df = load()
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 20)

    print("== Coverage (World Bank, economies only) ==")
    print(coverage(df).to_string(index=False))
    ref = latest_common_year(df, ["ppp", "life_exp", "pop"])
    table_year = latest_common_year(df, TABLE_COLUMNS)
    print(f"\nLatest year with broad coverage of income, life expectancy and population: {ref}; of all table columns: {table_year}")

    print("\n== Preston curve: life expectancy = a + b * ln(GDP per capita, PPP); robust (HC1) standard errors ==")
    fits = {}
    for year in (1990, ref):
        fit = fits[year] = fit_preston(df, year)
        quad = fit_preston(df, year, curvature=True)
        print(f"{year}: n={fit.n}  a={fit.coef('const'):.2f} (se {fit.se('const'):.2f})  b={fit.coef('ln_income'):.2f} (se {fit.se('ln_income'):.2f})  "
              f"R2={fit.r2:.3f}  doubling income = +{fit.coef('ln_income') * math.log(2):.2f} years  "
              f"| curvature term {quad.coef('ln_income_sq'):.3f} (p={quad.p('ln_income_sq'):.3f})")
    for income in (1000, 5000, 20000):
        a, b = (preston_curve(fits[y], [income])[0] for y in (1990, ref))
        print(f"predicted life expectancy at ${income:,}: {a:.1f} in 1990, {b:.1f} in {ref} ({b - a:+.1f})")
    over_time = preston_over_time(df, 1990, ref).set_index("year")
    print("slope by year: " + ", ".join(f"{y}={over_time.loc[y, 'slope']:.2f}" for y in (1990, 2000, 2010, 2020, ref)))

    print(f"\n== Country comparison, {table_year} ==")
    show = comparison_table(df, ["USA", "CHN", "IND", "NGA", "BRA", "NOR"], table_year)
    print(show.drop(columns="region").to_string(index=False, float_format=lambda v: f"{v:,.1f}"))

    print("\n== Absolute beta-convergence: annual log growth (% per year) on ln(initial PPP income) ==")
    for label, kwargs in {"all countries": {}, "population >= 1 million": {"min_population": 1e6}, "population-weighted": {"weighted": True}}.items():
        reg, sample = beta_convergence(df, 1990, ref, **kwargs)
        speed = convergence_speed(reg.coef("ln_initial"), ref - 1990)
        extra = f"  speed {speed[0] * 100:.2f}%/yr, half-life {speed[1]:.0f} years" if speed else ""
        print(f"1990-{ref} {label:24s} n={reg.n:3d}  beta={reg.coef('ln_initial'):.3f} (se {reg.se('ln_initial'):.3f}, p={reg.p('ln_initial'):.4f})  "
              f"R2={reg.r2:.3f}  const={reg.coef('const'):.2f}{extra}")
    windows = convergence_by_window(df, [(1990, 2000), (2000, 2010), (2010, ref)])
    print("By sub-period (all countries):")
    print(windows.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    reg, sample = beta_convergence(df, 1990, ref)
    fastest = sample.sort_values("growth", ascending=False).head(3)
    print("Fastest growers 1990-%d: " % ref + ", ".join(f"{r.country} {r.growth:.1f}%" for r in fastest.itertuples()))

    print("\n== Population-weighted Gini of GDP per capita (PPP) across countries ==")
    g = weighted_gini_by_year(df).set_index("year")
    for year in (1990, 2000, 2010, ref):
        row = g.loc[year]
        print(f"{year}: weighted {row['gini_weighted']:.3f}  unweighted {row['gini_unweighted']:.3f}  countries {int(row['n'])}  population covered {row['pop_share_covered']:.1%}")
    for label, exclude in {"excluding China": ["CHN"], "excluding China and India": ["CHN", "IND"]}.items():
        x = weighted_gini_by_year(df, exclude).set_index("year")
        print(f"{label}: {x.loc[1990, 'gini_weighted']:.3f} in 1990, {x.loc[ref, 'gini_weighted']:.3f} in {ref}")


if __name__ == "__main__":
    main()
