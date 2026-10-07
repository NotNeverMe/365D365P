"""Government spending by function and by economic category.

Two different questions are answered by two different kinds of data, and they use
different denominators, so they are never added together here:

* **By function** (what the money is for), as a percentage of GDP: education, government
  health and military spending from the World Bank, plus the full ten-division COFOG
  breakdown from Eurostat for 30 European countries.
* **By economic category** (what the money is spent on), as a percentage of *total central
  government expense*: pay, goods and services, interest, subsidies and transfers, other.

Run ``python projects/010-government-spending-explorer/gov_spending.py`` for the summary
quoted in the README.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd

from core import worldbank as wb
from core.http import get
from core.paths import DATA

GDP = "% of GDP"
EXPENSE = "% of total expense"


@dataclass(frozen=True)
class Series:
    """One World Bank indicator used by the project."""

    key: str
    code: str
    label: str
    group: str  # "context", "function" or "economic"
    denominator: str
    scope: str  # which level of government the figure covers


SERIES: tuple[Series, ...] = (
    Series("expense", "GC.XPN.TOTL.GD.ZS", "Total expense", "context", GDP, "central government"),
    Series("education", "SE.XPD.TOTL.GD.ZS", "Education", "function", GDP, "general government"),
    Series("health", "SH.XPD.GHED.GD.ZS", "Health (government-funded)", "function", GDP, "general government"),
    Series("military", "MS.MIL.XPND.GD.ZS", "Military", "function", GDP, "government (SIPRI definition)"),
    Series("compensation", "GC.XPN.COMP.ZS", "Compensation of employees", "economic", EXPENSE, "central government"),
    Series("goods_services", "GC.XPN.GSRV.ZS", "Goods and services", "economic", EXPENSE, "central government"),
    Series("interest", "GC.XPN.INTP.ZS", "Interest payments", "economic", EXPENSE, "central government"),
    Series("transfers", "GC.XPN.TRFT.ZS", "Subsidies and other transfers", "economic", EXPENSE, "central government"),
    Series("other", "GC.XPN.OTHR.ZS", "Other expense", "economic", EXPENSE, "central government"),
)
BY_KEY = {s.key: s for s in SERIES}
FUNCTION_KEYS = [s.key for s in SERIES if s.group == "function"]
ECONOMIC_KEYS = [s.key for s in SERIES if s.group == "economic"]


def labels() -> dict[str, str]:
    """Map series key to a display label."""
    return {s.key: s.label for s in SERIES}


def load(*, refresh: bool = False) -> pd.DataFrame:
    """Wide frame indexed by (iso3, year), one column per entry in ``SERIES``. Economies only."""
    return wb.indicators({s.key: s.code for s in SERIES}, refresh=refresh)


def economic_in_gdp(df: pd.DataFrame) -> pd.DataFrame:
    """Economic categories re-expressed as % of GDP: share of expense x expense (% of GDP) / 100.

    Only meaningful because both factors describe the same central government. Columns are
    named ``<key>_gdp`` so they cannot be confused with the original shares.
    """
    out = pd.DataFrame(index=df.index)
    for key in ECONOMIC_KEYS:
        out[f"{key}_gdp"] = df[key] / 100.0 * df["expense"]
    return out


# ----------------------------------------------------------------------------- coverage


def coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per series: first/last year, countries ever covered, and the year with the widest coverage."""
    n_economies = len(wb.names())
    rows = []
    for s in SERIES:
        col = df[s.key].dropna()
        years = col.index.get_level_values("year")
        countries = col.index.get_level_values("iso3").nunique()
        per_year = col.groupby(level="year").size()
        rows.append(
            {
                "series": s.label,
                "denominator": s.denominator,
                "first_year": int(years.min()) if len(col) else None,
                "last_year": int(years.max()) if len(col) else None,
                "countries": int(countries),
                "share_of_economies": countries / n_economies,
                "best_year": int(per_year.idxmax()) if len(col) else None,
                "countries_in_best_year": int(per_year.max()) if len(col) else 0,
            }
        )
    return pd.DataFrame(rows)


def broad_year(df: pd.DataFrame, key: str, min_countries: int = 100) -> int:
    """Latest year in which at least ``min_countries`` countries report ``key``."""
    per_year = df[key].dropna().groupby(level="year").size()
    eligible = per_year[per_year >= min_countries]
    if eligible.empty:
        raise ValueError(f"no year has {min_countries} countries for {key!r}")
    return int(eligible.index.max())


def economic_sum_check(df: pd.DataFrame) -> pd.Series:
    """Sum of the five economic shares for rows where all five are reported (should be 100)."""
    five = df[ECONOMIC_KEYS].dropna()
    return five.sum(axis=1).rename("sum_of_shares")


# ------------------------------------------------------------------- picking observations


def latest_on_or_before(df: pd.DataFrame, key: str, iso3: str, year: int, max_lag: int = 0) -> tuple[float, int | None]:
    """Latest observation of ``key`` for one country in ``[year - max_lag, year]``.

    Returns ``(value, observation_year)``, or ``(nan, None)`` when nothing is reported. Nothing is
    interpolated: the observation year is always returned so callers can show it.
    """
    try:
        col = df[key].xs(iso3, level="iso3").dropna()
    except KeyError:
        return float("nan"), None
    col = col[(col.index <= year) & (col.index >= year - max_lag)]
    if col.empty:
        return float("nan"), None
    return float(col.iloc[-1]), int(col.index[-1])


def snapshot(df: pd.DataFrame, iso3: str, year: int, max_lag: int = 0) -> pd.DataFrame:
    """What one country reports in ``year``: one row per series, with its denominator and source year."""
    rows = []
    for s in SERIES:
        value, obs_year = latest_on_or_before(df, s.key, iso3, year, max_lag)
        rows.append(
            {
                "key": s.key,
                "indicator": s.label,
                "group": s.group,
                "denominator": s.denominator,
                "scope": s.scope,
                "value": value,
                "observation_year": obs_year,
            }
        )
    out = pd.DataFrame(rows)
    out["observation_year"] = out["observation_year"].astype("Int64")
    return out


def cross_section(df: pd.DataFrame, key: str, year: int) -> pd.DataFrame:
    """All countries reporting ``key`` in exactly ``year``, largest first (iso3, country, value)."""
    col = df[key].dropna()
    try:
        col = col.xs(year, level="year")
    except KeyError:
        return pd.DataFrame(columns=["iso3", "country", "value"])
    out = col.rename("value").reset_index()
    out["country"] = out["iso3"].map(wb.names())
    return out.sort_values("value", ascending=False).reset_index(drop=True)[["iso3", "country", "value"]]


def trend(df: pd.DataFrame, keys: list[str], iso3s: list[str], first: int, last: int) -> pd.DataFrame:
    """Tidy long frame (iso3, country, year, indicator, value) for charting trends."""
    sub = df.loc[df.index.get_level_values("iso3").isin(iso3s), keys].reset_index()
    sub = sub[(sub["year"] >= first) & (sub["year"] <= last)]
    long = sub.melt(id_vars=["iso3", "year"], value_vars=keys, var_name="key", value_name="value").dropna(subset=["value"])
    long["country"] = long["iso3"].map(wb.names())
    long["indicator"] = long["key"].map(labels())
    return long.sort_values(["iso3", "key", "year"]).reset_index(drop=True)


def interest_ranking(df: pd.DataFrame, year: int, top: int = 15) -> pd.DataFrame:
    """Countries where interest takes the largest share of central government expense in ``year``.

    Columns: iso3, country, interest_share (% of expense), interest_gdp (% of GDP, derived as
    share x expense / 100, NaN when expense is missing) and expense_gdp.
    """
    sub = df.xs(year, level="year")[["interest", "expense"]].dropna(subset=["interest"])
    sub = sub.assign(interest_gdp=sub["interest"] / 100.0 * sub["expense"])
    sub = sub.rename(columns={"interest": "interest_share", "expense": "expense_gdp"}).reset_index()
    sub["country"] = sub["iso3"].map(wb.names())
    sub = sub.sort_values("interest_share", ascending=False).head(top).reset_index(drop=True)
    return sub[["iso3", "country", "interest_share", "interest_gdp", "expense_gdp"]]


def median_by_year(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Cross-country median of each series per year, with the number of countries behind it."""
    out = {}
    for key in keys:
        grouped = df[key].dropna().groupby(level="year")
        out[f"{key}_median"] = grouped.median()
        out[f"{key}_n"] = grouped.size()
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- COFOG (Eurostat)

EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/gov_10a_exp/A.PC_GDP+PC_TOT.S13..TE."
COFOG_CACHE = DATA / "eurostat" / "gov_10a_exp_cofog.csv.gz"

COFOG_LABELS = {
    "GF01": "General public services",
    "GF02": "Defence",
    "GF03": "Public order and safety",
    "GF04": "Economic affairs",
    "GF05": "Environmental protection",
    "GF06": "Housing and community amenities",
    "GF07": "Health",
    "GF08": "Recreation, culture and religion",
    "GF09": "Education",
    "GF10": "Social protection",
}
EUROSTAT_TO_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CH": "CHE", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "EE": "EST", "EL": "GRC", "ES": "ESP", "FI": "FIN", "FR": "FRA", "HR": "HRV", "HU": "HUN", "IE": "IRL",
    "IS": "ISL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT", "NL": "NLD", "NO": "NOR",
    "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK",
}  # aggregates such as EA20 and EU27_2020 are dropped on purpose


def parse_cofog(csv_text: str) -> pd.DataFrame:
    """Tidy COFOG frame from Eurostat SDMX-CSV: iso3, year, cofog, unit, value, flag.

    Keeps the ten first-level divisions plus ``TOTAL`` and countries (not aggregates).
    ``unit`` is ``pc_gdp`` or ``pc_total`` (percentage of total expenditure).
    """
    raw = pd.read_csv(io.StringIO(csv_text), dtype={"OBS_FLAG": "string"})
    keep = raw["cofog99"].isin([*COFOG_LABELS, "TOTAL"]) & raw["geo"].isin(EUROSTAT_TO_ISO3)
    raw = raw[keep]
    out = pd.DataFrame(
        {
            "iso3": raw["geo"].map(EUROSTAT_TO_ISO3),
            "year": raw["TIME_PERIOD"].astype(int),
            "cofog": raw["cofog99"],
            "unit": raw["unit"].map({"PC_GDP": "pc_gdp", "PC_TOT": "pc_total"}),
            "value": pd.to_numeric(raw["OBS_VALUE"], errors="coerce"),
            "flag": raw["OBS_FLAG"].fillna(""),
        }
    )
    return out.dropna(subset=["value"]).sort_values(["iso3", "year", "unit", "cofog"]).reset_index(drop=True)


def load_cofog(*, refresh: bool = False) -> pd.DataFrame:
    """Eurostat COFOG (table gov_10a_exp, general government), cached under ``data/eurostat/``."""
    if COFOG_CACHE.exists() and not refresh:
        return pd.read_csv(COFOG_CACHE).fillna({"flag": ""})
    frame = parse_cofog(get(EUROSTAT_URL, params={"format": "SDMX-CSV"}, timeout=180).text)
    COFOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(COFOG_CACHE, index=False, compression="gzip")
    return frame


def cofog_snapshot(cofog: pd.DataFrame, iso3: str, year: int) -> pd.DataFrame:
    """Ten COFOG divisions for one country-year: pc_gdp, pc_total and the label.

    Empty when the country or year is not in the Eurostat table.
    """
    sub = cofog[(cofog["iso3"] == iso3) & (cofog["year"] == year) & (cofog["cofog"] != "TOTAL")]
    wide = sub.pivot(index="cofog", columns="unit", values="value").reindex(list(COFOG_LABELS)).dropna(how="all")
    wide.insert(0, "division", [COFOG_LABELS[c] for c in wide.index])
    return wide.reset_index()


def cofog_total(cofog: pd.DataFrame, iso3: str, year: int) -> float:
    """Total general government expenditure in % of GDP, as reported by Eurostat (NaN if absent)."""
    sub = cofog[(cofog["iso3"] == iso3) & (cofog["year"] == year) & (cofog["cofog"] == "TOTAL") & (cofog["unit"] == "pc_gdp")]
    return float(sub["value"].iloc[0]) if len(sub) else float("nan")


def scope_comparison(df: pd.DataFrame, cofog: pd.DataFrame, year: int) -> pd.DataFrame:
    """Central government expense (World Bank) next to general government expenditure (Eurostat), both % of GDP.

    Shows why series with different scope cannot be mixed: the same country can look 20 points of
    GDP smaller depending on which level of government is counted.
    """
    total = cofog[(cofog["cofog"] == "TOTAL") & (cofog["unit"] == "pc_gdp") & (cofog["year"] == year)]
    general = total.set_index("iso3")["value"].rename("general_government")
    try:
        central = df["expense"].xs(year, level="year").dropna().rename("central_government")
    except KeyError:
        return pd.DataFrame(columns=["iso3", "country", "central_government", "general_government", "central_share_of_general"])
    out = pd.concat([central, general], axis=1, join="inner").reset_index(names="iso3")
    out["central_share_of_general"] = out["central_government"] / out["general_government"]
    out["country"] = out["iso3"].map(wb.names())
    return out[["iso3", "country", "central_government", "general_government", "central_share_of_general"]]


# ------------------------------------------------------------------------------------ summary


def main() -> None:
    df = load()
    names = wb.names()
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)

    print("== Coverage (World Bank, economies only) ==")
    print(coverage(df).to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    sums = economic_sum_check(df)
    within = ((sums - 100).abs() <= 1.0).mean()
    print(f"\n== Do the five economic shares add to 100? == rows with all five reported: {len(sums)}; "
          f"within 1 point of 100: {within:.1%}; median sum {sums.median():.2f}")

    year = broad_year(df, "interest")
    print(f"\n== Interest payments, share of central government expense, {year} "
          f"({len(cross_section(df, 'interest', year))} countries) ==")
    print(interest_ranking(df, year, top=10).to_string(index=False, float_format=lambda v: f"{v:.1f}"))
    sec = cross_section(df, "interest", year)
    print(f"median across countries: {sec['value'].median():.1f}% of expense")

    print("\n== Cross-country medians, latest broad year per series ==")
    for key in ["expense", "education", "health", "military", "compensation", "goods_services", "interest", "transfers", "other"]:
        y = broad_year(df, key)
        sec = cross_section(df, key, y)
        top = sec.iloc[0]
        print(f"{BY_KEY[key].label:32s} {BY_KEY[key].denominator:20s} {y}  n={len(sec):3d}  "
              f"median={sec['value'].median():5.1f}  highest={top['country']} {top['value']:.1f}")

    print("\n== Economic categories converted to % of GDP (share x expense / 100), by country, latest broad year ==")
    gdp = economic_in_gdp(df)
    y = broad_year(df, "interest")
    for iso in ["USA", "GBR", "DEU", "JPN", "IND", "BRA"]:
        if (iso, y) in gdp.index:
            row = gdp.loc[(iso, y)]
            print(f"{names[iso]:16s} " + "  ".join(f"{k}={row[f'{k}_gdp']:.1f}" for k in ECONOMIC_KEYS)
                  + f"  expense={df.loc[(iso, y), 'expense']:.1f}")

    cofog = load_cofog()
    last = int(cofog["year"].max())
    covered = cofog[(cofog["cofog"] == "TOTAL") & (cofog["unit"] == "pc_gdp")].groupby("year")["iso3"].nunique()
    print(f"\n== COFOG (Eurostat gov_10a_exp, general government): {cofog['iso3'].nunique()} countries, "
          f"{cofog['year'].min()}-{last}; countries per year: " + ", ".join(f"{y}={n}" for y, n in covered.tail(4).items()))
    wide_year = int(covered[covered >= 25].index.max())
    snap = cofog[(cofog["year"] == wide_year) & (cofog["unit"] == "pc_total") & (cofog["cofog"] != "TOTAL")]
    mean_share = snap.groupby("cofog")["value"].mean().rename(index=COFOG_LABELS).sort_values(ascending=False)
    print(f"Average share of total expenditure by function across {snap['iso3'].nunique()} European countries in {wide_year}:")
    print(mean_share.round(1).to_string())
    for iso in ["DEU", "FRA", "IRL"]:
        shot = cofog_snapshot(cofog, iso, wide_year).sort_values("pc_gdp", ascending=False)
        top = shot.iloc[0]
        print(f"{names[iso]} {wide_year}: total {cofog_total(cofog, iso, wide_year):.1f}% of GDP; largest function "
              f"{top['division']} {top['pc_gdp']:.1f}% of GDP ({top['pc_total']:.1f}% of expenditure)")

    print(f"\n== Scope trap: central government expense (World Bank) vs general government expenditure (Eurostat), {wide_year - 2} ==")
    scope = scope_comparison(df, cofog, wide_year - 2)
    print(f"{len(scope)} countries in both; median central/general = {scope['central_share_of_general'].median():.2f}")
    print(scope[scope["iso3"].isin(["DEU", "FRA", "ESP", "NLD", "SWE"])].to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    g20 = ["ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN", "ITA", "JPN", "KOR", "MEX", "RUS", "SAU", "ZAF", "TUR", "GBR", "USA"]
    missing = [names[c] for c in g20 if (c, year) not in df["interest"].dropna().index]
    print(f"\n== Large economies (G20 members except the EU/AU) with no interest-payment figure in {year}: {', '.join(missing)} ==")


if __name__ == "__main__":
    main()
