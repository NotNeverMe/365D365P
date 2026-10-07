"""Purchasing power: how much can a currency actually buy?

Builds a price level index from World Bank PPP conversion factors and official exchange rates,

    price level = PPP conversion factor / exchange rate x 100        (United States = 100)

checks it against the World Bank's published price level index and against the Big Mac index, converts
money "at market rates" versus "at PPP", compares nominal with PPP income, and fits the Penn effect
(richer countries have higher price levels) with statsmodels.

Run ``python projects/006-purchasing-power-explorer/purchasing_power.py`` to print the numbers quoted in the README.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm

from core import bigmac
from core import worldbank as wb

WB_CODES = {
    "ppp": "PA.NUS.PPP",  # PPP conversion factor, GDP (local currency units per international $)
    "fx": "PA.NUS.FCRF",  # official exchange rate (local currency units per US$, period average)
    "price_level_published": "PA.NUS.GDP.PLI",  # World Bank price level index, GDP (US = 100)
    "gdp_nominal": "NY.GDP.PCAP.CD",  # GDP per capita, current US$
    "gdp_ppp": "NY.GDP.PCAP.PP.CD",  # GDP per capita, PPP, current international $
}
# Own and published price levels may differ by this many index points before a country-year is flagged.
CONSISTENCY_TOLERANCE = 1.0


# ------------------------------------------------------------------ price level


def price_level(ppp, fx):
    """Price level index, United States = 100: how much a basket costs in a country relative to the US.

    Below 100 the country is cheaper than the US at market exchange rates, and its currency buys more at home
    than its exchange rate suggests. Works on numbers, arrays and Series.
    """
    return ppp / fx * 100.0


def build_panel(*, refresh: bool = False) -> pd.DataFrame:
    """One row per country-year: PPP factor, exchange rate, own and published price level, incomes.

    ``consistent`` is True where our price level is within :data:`CONSISTENCY_TOLERANCE` points of the
    World Bank's published index. It is False where the two disagree or the published value is missing,
    which in practice marks currency-unit mismatches between the PPP and exchange-rate series (for example
    after a redenomination) that make PPP / exchange rate meaningless.
    """
    wide = wb.indicators(WB_CODES, refresh=refresh).reset_index()
    wide["country"] = wide["iso3"].map(wb.names())
    wide["price_level"] = price_level(wide["ppp"], wide["fx"])
    gap = (wide["price_level"] - wide["price_level_published"]).abs()
    wide["consistent"] = gap <= CONSISTENCY_TOLERANCE
    cols = ["iso3", "country", "year", "ppp", "fx", "price_level", "price_level_published", "consistent", "gdp_nominal", "gdp_ppp"]
    return wide[cols]


def regions() -> pd.Series:
    """World Bank region for each iso3 (for colouring charts)."""
    meta = wb.countries().query("not is_aggregate")
    return pd.Series(meta["region"].to_numpy(), index=meta["iso3"], name="region")


def latest_complete_year(panel: pd.DataFrame, column: str = "price_level", share: float = 0.9) -> int:
    """Latest year in which at least ``share`` of the best-covered year's countries have a value."""
    counts = panel.dropna(subset=[column]).groupby("year")["iso3"].nunique()
    return int(counts[counts >= share * counts.max()].index.max())


def year_slice(panel: pd.DataFrame, year: int) -> pd.DataFrame:
    return panel[panel["year"] == year].set_index("iso3")


def ppp_valuation(level) -> object:
    """Over/undervaluation of a currency against the US dollar implied by the price level, as a fraction.

    -0.60 means prices are 60% below US prices at market rates: the currency is 60% undervalued at PPP.
    """
    return level / 100.0 - 1.0


def consistency_report(panel: pd.DataFrame) -> dict[str, object]:
    """How often our price level matches the World Bank's published one, and which countries break it most."""
    have = panel.dropna(subset=["price_level", "price_level_published"])
    off = have[~have["consistent"]]
    return {
        "n": len(have),
        "share_consistent": float(have["consistent"].mean()),
        "offenders": off.groupby("country").size().sort_values(ascending=False),
    }


def income_identity_gap(panel: pd.DataFrame) -> pd.Series:
    """Relative gap between the PPP/nominal income ratio and its theoretical value, 100 / price level.

    Both incomes come from the same national accounts, so GDP per capita (PPP) / GDP per capita (nominal)
    must equal exchange rate / PPP factor = 100 / price level. The gap should be about zero wherever the
    currency units agree.
    """
    have = panel.dropna(subset=["price_level", "gdp_nominal", "gdp_ppp"])
    have = have[have["price_level"] > 0]
    return (have["gdp_ppp"] / have["gdp_nominal"]) / (100.0 / have["price_level"]) - 1.0


# ------------------------------------------------------------------ Big Mac


def bigmac_releases() -> pd.DataFrame:
    """Every Big Mac release (January and July), euro area removed, with a US-relative price level."""
    raw = bigmac.load()
    us = raw.loc[raw["iso_a3"] == "USA"].set_index("date")["dollar_price"]
    raw = raw[raw["iso_a3"] != "EUZ"].copy()
    raw["bigmac_level"] = raw["dollar_price"] / raw["date"].map(us) * 100.0
    cols = ["date", "iso_a3", "name", "dollar_price", "USD_raw", "USD_adjusted", "adj_price", "bigmac_level"]
    return raw[cols].rename(columns={"iso_a3": "iso3"}).reset_index(drop=True)


def bigmac_annual(releases: pd.DataFrame | None = None) -> pd.DataFrame:
    """Big Mac price level by country-year (mean of that year's January and July releases)."""
    releases = bigmac_releases() if releases is None else releases
    annual = releases.assign(year=releases["date"].dt.year).groupby(["iso3", "year"], as_index=False)["bigmac_level"].mean()
    return annual


def crosscheck_bigmac(panel: pd.DataFrame, year: int, annual: pd.DataFrame | None = None) -> pd.DataFrame:
    """Own price level beside the Big Mac price level for countries with both, flagged rows excluded."""
    annual = bigmac_annual() if annual is None else annual
    own = year_slice(panel, year)
    own = own[own["consistent"]][["country", "price_level"]]
    merged = own.join(annual[annual["year"] == year].set_index("iso3")["bigmac_level"], how="inner")
    merged["ratio"] = merged["bigmac_level"] / merged["price_level"]
    return merged.reset_index()


def crosscheck_summary(merged: pd.DataFrame) -> dict[str, float]:
    return {
        "n": len(merged),
        "spearman": float(merged["price_level"].corr(merged["bigmac_level"], method="spearman")),
        "pearson": float(merged["price_level"].corr(merged["bigmac_level"])),
        "median_ratio": float(merged["ratio"].median()),
    }


def crosscheck_by_year(panel: pd.DataFrame, years: range | list[int] | None = None) -> pd.DataFrame:
    """Cross-check statistics for each year with enough overlap."""
    annual = bigmac_annual()
    years = years if years is not None else sorted(set(annual["year"]) & set(panel["year"]))
    rows = []
    for year in years:
        merged = crosscheck_bigmac(panel, year, annual)
        if len(merged) >= 10:
            rows.append({"year": year, **crosscheck_summary(merged)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ converter and incomes


@dataclass(frozen=True)
class Conversion:
    """What an amount of US dollars is worth in a country, at market rates and at PPP."""

    amount_usd: float
    market_lcu: float  # local currency received at the market exchange rate
    ppp_lcu: float  # local currency needed to buy what the same dollars buy in the US
    purchasing_power: float  # US-price dollars' worth of goods the market-rate amount buys locally

    @property
    def multiplier(self) -> float:
        """How many times more (or less) the dollars buy locally than in the US."""
        return self.purchasing_power / self.amount_usd


def convert(amount_usd: float, ppp: float, fx: float) -> Conversion:
    """Convert dollars at the market rate and at PPP.

    ``fx`` is local currency units per US dollar at the market rate, ``ppp`` the local currency units
    that buy what one US dollar buys in the US. At market rates ``amount`` dollars become ``amount * fx``
    units, which buy ``amount * fx / ppp`` dollars' worth of US-priced goods.
    """
    if amount_usd < 0:
        raise ValueError("amount must not be negative")
    if not (ppp > 0 and fx > 0):
        raise ValueError("PPP factor and exchange rate must be positive")
    return Conversion(amount_usd, amount_usd * fx, amount_usd * ppp, amount_usd * fx / ppp)


def big_macs(amount_usd: float, dollar_price: float) -> float:
    """How many Big Macs an amount of dollars buys at a local dollar-equivalent price."""
    if dollar_price <= 0:
        raise ValueError("price must be positive")
    return amount_usd / dollar_price


def income_table(panel: pd.DataFrame, year: int, iso3s: list[str] | None = None) -> pd.DataFrame:
    """Nominal and PPP income per head, their ratio, and the ratio implied by the price level."""
    snap = year_slice(panel, year)
    if iso3s is not None:
        snap = snap.loc[snap.index.intersection(iso3s)]
    out = snap[["country", "gdp_nominal", "gdp_ppp", "price_level"]].dropna(subset=["gdp_nominal", "gdp_ppp"]).copy()
    out["ppp_over_nominal"] = out["gdp_ppp"] / out["gdp_nominal"]
    return out.reset_index()


# ------------------------------------------------------------------ the Penn effect


@dataclass(frozen=True)
class PennFit:
    """OLS of ln(price level) on ln(income per head), with heteroskedasticity-robust (HC1) errors."""

    slope: float
    intercept: float
    slope_se: float
    r_squared: float
    n: int
    p_value: float

    def predict(self, income) -> np.ndarray:
        """Fitted price level (index points) at the given income."""
        return np.exp(self.intercept + self.slope * np.log(np.asarray(income, dtype=float)))

    @property
    def ten_percent_effect(self) -> float:
        """Percentage change in the price level associated with 10% higher income."""
        return (1.1**self.slope - 1.0) * 100.0

    @property
    def ci95(self) -> tuple[float, float]:
        return self.slope - 1.96 * self.slope_se, self.slope + 1.96 * self.slope_se


def penn_sample(panel: pd.DataFrame, year: int, income: str = "gdp_ppp") -> pd.DataFrame:
    """Countries usable for the regression: consistent price level, positive income."""
    snap = year_slice(panel, year)
    snap = snap[snap["consistent"] & (snap["price_level"] > 0) & (snap[income] > 0)]
    return snap.dropna(subset=["price_level", income])


def penn_fit(sample: pd.DataFrame, income: str = "gdp_ppp") -> PennFit:
    """Fit ln(price level) = a + b ln(income). ``b`` is the elasticity of prices with respect to income."""
    if len(sample) < 10:
        raise ValueError("need at least 10 countries to fit the Penn effect")
    x = sm.add_constant(np.log(sample[income].to_numpy(dtype=float)))
    y = np.log(sample["price_level"].to_numpy(dtype=float))
    model = sm.OLS(y, x).fit(cov_type="HC1")
    return PennFit(
        slope=float(model.params[1]),
        intercept=float(model.params[0]),
        slope_se=float(model.bse[1]),
        r_squared=float(model.rsquared),
        n=int(model.nobs),
        p_value=float(model.pvalues[1]),
    )


def penn_by_year(panel: pd.DataFrame, income: str = "gdp_ppp", first_year: int = 1995) -> pd.DataFrame:
    """The fitted slope for every year with at least 30 countries."""
    rows = []
    for year in sorted(panel["year"].unique()):
        if year < first_year:
            continue
        sample = penn_sample(panel, int(year), income)
        if len(sample) >= 30:
            fit = penn_fit(sample, income)
            rows.append({"year": int(year), "slope": fit.slope, "se": fit.slope_se, "r_squared": fit.r_squared, "n": fit.n})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ command line


def main() -> None:
    panel = build_panel()
    year = latest_complete_year(panel)
    snap = year_slice(panel, year)
    print(f"WORLD BANK PANEL: {panel['iso3'].nunique()} economies, {panel['year'].min()}-{panel['year'].max()}")
    print(f"  price level (PPP / exchange rate x 100) computable for {snap['price_level'].notna().sum()} economies in {year} (latest year with at least 90% of peak coverage)")

    rep = consistency_report(panel)
    print(f"\nOwn price level vs World Bank published index: {rep['share_consistent']:.1%} of {rep['n']} country-years agree within {CONSISTENCY_TOLERANCE:g} point")
    print("  most frequent mismatches (country-years):", ", ".join(f"{c} {n}" for c, n in rep["offenders"].head(6).items()))
    for country in list(rep["offenders"].head(3).index):
        rows = panel[(panel["country"] == country) & panel["price_level"].notna() & ~panel["consistent"]]
        ratio = (rows["price_level_published"] / rows["price_level"]).median()
        print(f"  {country}: published / own price level has median {ratio:.2f} over {len(rows)} flagged years")
    consistent = panel[panel["consistent"]]
    gap = income_identity_gap(consistent)
    gap_now = income_identity_gap(consistent[consistent["year"] == year])
    print(
        f"Identity PPP income / nominal income = 100 / price level on consistent rows: all years median gap {gap.abs().median():.1e}, "
        f"{(gap.abs() < 0.01).mean():.1%} of {len(gap)} within 1%; in {year}, {(gap_now.abs() < 0.01).mean():.1%} of {len(gap_now)} within 1%"
    )

    usable = snap[snap["consistent"]]["price_level"].dropna().sort_values()

    def named(codes) -> str:
        return ", ".join(f"{snap.loc[i, 'country']} {usable[i]:.1f}" for i in codes)

    print(f"\nPRICE LEVELS {year} ({len(usable)} consistent economies) lowest: {named(usable.index[:3])}; highest: {named(usable.index[-3:])}")

    merged = crosscheck_bigmac(panel, year)
    s = crosscheck_summary(merged)
    print(f"\nCROSS-CHECK vs BIG MAC, {year}: {s['n']} countries in both: Spearman {s['spearman']:.2f}, Pearson {s['pearson']:.2f}, median Big Mac / own price level {s['median_ratio']:.2f}")
    by_year = crosscheck_by_year(panel, range(2005, year + 1))
    print(f"  Spearman by year 2005-{year}: min {by_year['spearman'].min():.2f}, max {by_year['spearman'].max():.2f}, mean {by_year['spearman'].mean():.2f}")

    releases = bigmac_releases()
    last = releases[releases["date"] == releases["date"].max()].set_index("iso3")
    print(f"\nOVER/UNDERVALUATION, Big Mac release {releases['date'].max():%B %Y} ({len(last)} economies; GDP-adjusted for {last['USD_adjusted'].notna().sum()}), vs US dollar")
    for col, label in [("USD_raw", "raw"), ("USD_adjusted", "GDP-adjusted")]:
        ranked = last[col].dropna().sort_values()
        lo, hi = ranked.head(3), ranked.tail(3)
        print(f"  {label:13s} most undervalued: " + ", ".join(f"{last.loc[i, 'name']} {v:+.0%}" for i, v in lo.items()))
        print(f"  {'':13s} most overvalued:  " + ", ".join(f"{last.loc[i, 'name']} {v:+.0%}" for i, v in hi.items()))

    print(f"\nCONVERTER, USD 100, {year}")
    for iso3 in ("IND", "CHN", "CHE", "DEU"):
        row = snap.loc[iso3]
        c = convert(100, row["ppp"], row["fx"])
        print(f"  {row['country']:12s} market {c.market_lcu:10,.1f} LCU | PPP {c.ppp_lcu:10,.1f} LCU | buys what USD {c.purchasing_power:,.0f} buys in the US (x{c.multiplier:.2f}), price level {row['price_level']:.1f}")

    inc = income_table(panel, year, ["USA", "CHE", "CHN", "IND", "BRA", "DEU", "NGA"]).set_index("iso3")
    print(f"\nINCOME PER HEAD {year}: nominal USD vs PPP international $")
    print(inc[["country", "gdp_nominal", "gdp_ppp", "ppp_over_nominal"]].round(2).to_string())

    sample = penn_sample(panel, year)
    fit = penn_fit(sample)
    lo, hi = fit.ci95
    print(f"\nPENN EFFECT {year}: ln(price level) on ln(PPP income per head), n={fit.n}")
    print(f"  slope {fit.slope:.3f} (HC1 s.e. {fit.slope_se:.3f}, 95% CI {lo:.3f} to {hi:.3f}), R-squared {fit.r_squared:.3f}, p={fit.p_value:.1e}")
    print(f"  10% higher income goes with a {fit.ten_percent_effect:.1f}% higher price level; fitted price level at USD 2,000 / 20,000 / 60,000 PPP income: " + " / ".join(f"{v:.0f}" for v in fit.predict([2000, 20000, 60000])))
    nominal = penn_fit(penn_sample(panel, year, "gdp_nominal"), "gdp_nominal")
    print(f"  same regression on nominal income (mechanically linked to price level): slope {nominal.slope:.3f}, R-squared {nominal.r_squared:.3f}")
    drop = len(year_slice(panel, year).dropna(subset=["price_level", "gdp_ppp"])) - fit.n
    print(f"  {drop} economies with a price level and income dropped as inconsistent")
    yearly = penn_by_year(panel, first_year=2000)
    print(f"  slope by year 2000-{year}: min {yearly['slope'].min():.3f} ({int(yearly.loc[yearly['slope'].idxmin(), 'year'])}), max {yearly['slope'].max():.3f} ({int(yearly.loc[yearly['slope'].idxmax(), 'year'])}), all positive and significant: {bool((yearly['slope'] - 1.96 * yearly['se'] > 0).all())}")


if __name__ == "__main__":
    main()
