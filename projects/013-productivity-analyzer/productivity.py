"""Labour productivity across countries and sectors.

Levels relative to the US, growth over a window, the productivity gap between
agriculture, industry and services, and a shift-share decomposition of
aggregate productivity growth into within-sector improvement and
between-sector structural change.

Data: World Bank WDI (output per worker, employment shares), Penn World Table
average annual hours via FRED, and US output per hour (FRED ``OPHNFB``).
Everything is a pure function of pandas objects; Streamlit lives in ``app.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core import fred
from core import worldbank as wb

BENCHMARK = "USA"
SECTORS = ["agr", "ind", "srv"]
SECTOR_NAMES = {"agr": "Agriculture", "ind": "Industry", "srv": "Services"}

WB_CODES = {
    "gdp_pe": "SL.GDP.PCAP.EM.KD",  # GDP per person employed, constant 2021 PPP $
    "va_agr": "NV.AGR.EMPL.KD",  # value added per worker, constant 2015 US$
    "va_ind": "NV.IND.EMPL.KD",
    "va_srv": "NV.SRV.EMPL.KD",
    "e_agr": "SL.AGR.EMPL.ZS",  # employment share, % of total employment (ILO modelled)
    "e_ind": "SL.IND.EMPL.ZS",
    "e_srv": "SL.SRV.EMPL.ZS",
}

# Penn World Table "average annual hours worked by persons engaged", republished on FRED as
# AVHWPE<ISO2>A065NRUG. Each id below was checked to exist. China and several others are not on FRED.
HOURS_ISO2_TO_ISO3 = {
    "US": "USA", "GB": "GBR", "DE": "DEU", "FR": "FRA", "IT": "ITA", "JP": "JPN", "CA": "CAN", "AU": "AUS",
    "KR": "KOR", "ES": "ESP", "NL": "NLD", "MX": "MEX", "TR": "TUR", "BR": "BRA", "IN": "IND", "PL": "POL",
    "SE": "SWE", "NO": "NOR", "DK": "DNK", "FI": "FIN", "AT": "AUT", "BE": "BEL", "CH": "CHE", "IE": "IRL",
    "PT": "PRT", "GR": "GRC", "CZ": "CZE", "HU": "HUN", "SK": "SVK", "SI": "SVN", "EE": "EST", "LV": "LVA",
    "LT": "LTU", "LU": "LUX", "IS": "ISL", "NZ": "NZL", "IL": "ISR", "CL": "CHL", "CO": "COL", "CR": "CRI",
    "AR": "ARG", "ZA": "ZAF", "ID": "IDN", "RU": "RUS", "TH": "THA", "MY": "MYS", "PH": "PHL", "VN": "VNM",
    "PK": "PAK", "BD": "BGD", "RO": "ROU", "BG": "BGR", "CY": "CYP", "MT": "MLT", "SG": "SGP", "HK": "HKG",
    "PE": "PER", "EC": "ECU", "UY": "URY", "VE": "VEN",
}  # fmt: skip

US_OUTPUT_PER_HOUR = "OPHNFB"  # nonfarm business output per hour of all workers, index 2017 = 100


# ------------------------------------------------------------------------------------ loading


def load() -> pd.DataFrame:
    """Wide World Bank frame indexed by (iso3, year) with the columns of ``WB_CODES``."""
    return wb.indicators(WB_CODES)


def load_hours() -> pd.DataFrame:
    """Average annual hours per person engaged: rows = year, columns = iso3 (Penn World Table via FRED)."""
    cols = {
        iso3: fred.series(f"AVHWPE{iso2}A065NRUG").groupby(lambda d: d.year).last()
        for iso2, iso3 in HOURS_ISO2_TO_ISO3.items()
    }
    out = pd.DataFrame(cols).sort_index()
    out.index.name = "year"
    return out


def load_us_output_per_hour() -> pd.Series:
    """US nonfarm business output per hour (index, 2017 = 100), annual average of quarters, indexed by year."""
    quarterly = fred.series(US_OUTPUT_PER_HOUR)
    counts = quarterly.groupby(quarterly.index.year).count()
    annual = quarterly.groupby(quarterly.index.year).mean()
    annual = annual[counts == 4]  # drop partial years
    annual.index.name = "year"
    return annual.rename("us_output_per_hour")


def level_matrix(wide: pd.DataFrame, column: str) -> pd.DataFrame:
    """Rows = year, columns = iso3 for one column of the wide frame."""
    return wide[column].unstack("iso3").sort_index()


# ------------------------------------------------------------------------------------ coverage


def coverage(wide: pd.DataFrame, total_economies: int | None = None) -> pd.DataFrame:
    """First/last year and number of economies with data, for every column of ``wide``."""
    if total_economies is None:
        total_economies = len(wb.names())
    rows = []
    for col in wide.columns:
        s = wide[col].dropna()
        years = s.index.get_level_values("year")
        iso = s.index.get_level_values("iso3")
        last = years.max()
        rows.append(
            {
                "indicator": col,
                "first_year": int(years.min()),
                "last_year": int(last),
                "economies_ever": iso.nunique(),
                "economies_in_last_year": iso[years == last].nunique(),
                "share_of_all_economies": iso.nunique() / total_economies,
            }
        )
    return pd.DataFrame(rows).set_index("indicator")


# ------------------------------------------------------------------------------------ levels and growth


def relative_to_benchmark(levels: pd.DataFrame, benchmark: str = BENCHMARK) -> pd.DataFrame:
    """Rescale every country so the benchmark (US) equals 100 in the same year. ``levels``: year x iso3."""
    if benchmark not in levels.columns:
        raise KeyError(f"{benchmark} is not in the data")
    return levels.div(levels[benchmark], axis=0) * 100.0


def window_cagr(levels: pd.DataFrame, start: int, end: int) -> pd.Series:
    """Compound annual growth (%) between two years, per country (NaN if either end year is missing or <= 0)."""
    if end <= start:
        raise ValueError("end year must be after start year")
    if start not in levels.index or end not in levels.index:
        return pd.Series(np.nan, index=levels.columns, name="cagr_pct")
    a, b = levels.loc[start], levels.loc[end]
    ok = (a > 0) & (b > 0)
    out = ((b[ok] / a[ok]) ** (1.0 / (end - start)) - 1.0) * 100.0
    return out.reindex(levels.columns).rename("cagr_pct")


def gdp_per_hour(gdp_per_worker: pd.DataFrame, hours: pd.DataFrame) -> pd.DataFrame:
    """Approximate GDP per hour worked: GDP per person employed divided by annual hours per person engaged.

    Both frames are year x iso3. Only country-years present in both are returned. This joins two
    sources (ILO/World Bank employment, Penn World Table hours), so treat levels as estimates.
    """
    common = gdp_per_worker.columns.intersection(hours.columns)
    years = gdp_per_worker.index.intersection(hours.index)
    return (gdp_per_worker.loc[years, common] / hours.loc[years, common]).dropna(how="all")


# ------------------------------------------------------------------------------------ sector gaps


def sector_table(wide: pd.DataFrame, year: int) -> pd.DataFrame:
    """Per-country sector productivity and employment shares in one year, plus gap measures.

    Columns: va_* (value added per worker), e_* (employment share, 0-1, rescaled to sum to 1),
    ``agg`` (employment-weighted average over the three sectors), ``ind_to_agr`` and ``srv_to_agr``
    (productivity ratios), ``max_to_min`` (best over worst sector) and ``apg``, the agricultural
    productivity gap: non-agricultural over agricultural value added per worker.
    """
    cols = [f"va_{s}" for s in SECTORS] + [f"e_{s}" for s in SECTORS]
    if year not in wide.index.get_level_values("year"):
        return pd.DataFrame(columns=cols)
    t = wide.xs(year, level="year")[cols].dropna()
    t = t[(t[[f"va_{s}" for s in SECTORS]] > 0).all(axis=1)]
    share_cols = [f"e_{s}" for s in SECTORS]
    t[share_cols] = t[share_cols].div(t[share_cols].sum(axis=1), axis=0)
    va = t[[f"va_{s}" for s in SECTORS]].to_numpy()
    e = t[share_cols].to_numpy()
    t["agg"] = (va * e).sum(axis=1)
    t["ind_to_agr"] = t["va_ind"] / t["va_agr"]
    t["srv_to_agr"] = t["va_srv"] / t["va_agr"]
    t["max_to_min"] = va.max(axis=1) / va.min(axis=1)
    nonag = (t["e_ind"] * t["va_ind"] + t["e_srv"] * t["va_srv"]) / (t["e_ind"] + t["e_srv"])
    t["apg"] = nonag / t["va_agr"]
    return t


# ------------------------------------------------------------------------------------ shift-share


def shift_share(p0: pd.DataFrame, p1: pd.DataFrame, s0: pd.DataFrame, s1: pd.DataFrame) -> pd.DataFrame:
    """Decompose the change in aggregate productivity P = sum_i s_i * p_i between two dates.

    Each argument has one row per economy and one column per sector: ``p`` is productivity per
    worker, ``s`` the employment share. Shares are rescaled to sum to one in every row. With
    delta p = p1 - p0 and delta s = s1 - s0:

        P1 - P0 = sum s0*dp  +  sum p0*ds  +  sum ds*dp
                  within       between       interaction

    * within: what the change would be if sectors improved but employment shares stayed at date 0;
    * between: what it would be if shares moved but sector productivity stayed at date 0 (moving
      workers out of low-productivity sectors counts here);
    * interaction: workers moving *into* sectors whose productivity itself changed.

    The three terms add up to the total change exactly (identity, not an approximation).
    Returns levels (same units as ``p``): ``P0``, ``P1``, ``total``, ``within``, ``between``, ``interaction``.
    """
    s0 = s0.div(s0.sum(axis=1), axis=0)
    s1 = s1.div(s1.sum(axis=1), axis=0)
    dp, ds = p1 - p0, s1 - s0
    out = pd.DataFrame(
        {
            "P0": (s0 * p0).sum(axis=1),
            "P1": (s1 * p1).sum(axis=1),
            "within": (s0 * dp).sum(axis=1),
            "between": (ds * p0).sum(axis=1),
            "interaction": (ds * dp).sum(axis=1),
        }
    )
    out["total"] = out["P1"] - out["P0"]
    return out[["P0", "P1", "total", "within", "between", "interaction"]]


def shift_share_window(wide: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """Shift-share for every economy with complete sector data in both years.

    Returns one row per economy: ``P0``, ``P1`` (constant 2015 US$ per worker), ``growth_pct``
    (total change relative to P0) and the three contributions in percentage points of that growth:
    ``within_pp``, ``between_pp``, ``interaction_pp`` (they sum to ``growth_pct``).
    """
    if end <= start:
        raise ValueError("end year must be after start year")
    t0, t1 = sector_table(wide, start), sector_table(wide, end)
    iso = t0.index.intersection(t1.index)
    if len(iso) == 0:
        return pd.DataFrame(columns=["P0", "P1", "growth_pct", "within_pp", "between_pp", "interaction_pp"])
    pcols, scols = [f"va_{s}" for s in SECTORS], [f"e_{s}" for s in SECTORS]
    ss = shift_share(t0.loc[iso, pcols], t1.loc[iso, pcols], t0.loc[iso, scols].set_axis(pcols, axis=1), t1.loc[iso, scols].set_axis(pcols, axis=1))
    out = pd.DataFrame({"P0": ss["P0"], "P1": ss["P1"], "growth_pct": ss["total"] / ss["P0"] * 100.0})
    for part in ["within", "between", "interaction"]:
        out[f"{part}_pp"] = ss[part] / ss["P0"] * 100.0
    return out


def add_metadata(table: pd.DataFrame) -> pd.DataFrame:
    """Attach country name, World Bank region and income group (index must be iso3)."""
    meta = wb.countries().set_index("iso3")[["name", "region", "income_group"]]
    return table.join(meta, how="left")


def summarise_by(table: pd.DataFrame, by: str, value_cols: list[str]) -> pd.DataFrame:
    """Median of ``value_cols`` and the number of economies, per group (``by`` is a column of ``table``)."""
    g = table.groupby(by)
    out = g[value_cols].median()
    out["economies"] = g.size()
    return out.sort_values(value_cols[0], ascending=False)


# ------------------------------------------------------------------------------------ summary


def _fmt(df: pd.DataFrame, **kw) -> str:
    return df.to_string(float_format=lambda v: f"{v:,.1f}", **kw)


def main() -> None:
    wide = load()
    hours = load_hours()
    us_oph = load_us_output_per_hour()
    names = wb.names()
    total = len(names)
    print(f"World Bank economies (non-aggregate): {total}")

    print("\n== Coverage (World Bank) ==")
    print(coverage(wide, total).to_string(float_format=lambda v: f"{v:.2f}"))
    print(f"\nPWT hours via FRED: {hours.shape[1]} countries, {hours.index.min()}-{hours.index.max()}")
    print(f"US output per hour (OPHNFB): {us_oph.index.min()}-{us_oph.index.max()} annual averages")
    usa_sector = wide[["va_agr", "va_ind", "va_srv"]].xs(BENCHMARK, level="iso3").dropna(how="all")
    print(f"US sector value added per worker: years with data = {list(usa_sector.index)}")

    # --- levels relative to the US
    pe = level_matrix(wide, "gdp_pe")
    rel = relative_to_benchmark(pe)
    year = 2023
    sample = ["USA", "NOR", "DEU", "FRA", "GBR", "JPN", "KOR", "POL", "MEX", "BRA", "CHN", "IND", "NGA"]
    hr = gdp_per_hour(pe, hours)
    rel_hr = relative_to_benchmark(hr)
    levels = pd.DataFrame(
        {
            "per_worker_PPP$": pe.loc[year, sample],
            "per_worker_US=100": rel.loc[year, sample],
            "hours_per_year": hours.loc[year, [c for c in sample if c in hours.columns]],
            "per_hour_PPP$": hr.loc[year, [c for c in sample if c in hr.columns]],
            "per_hour_US=100": rel_hr.loc[year, [c for c in sample if c in rel_hr.columns]],
        }
    )
    levels.index = [names.get(i, i) for i in levels.index]
    print(f"\n== GDP per person employed vs per hour worked, {year} (2021 PPP $) ==")
    print(_fmt(levels))
    both_year = pd.concat([rel.loc[year], rel_hr.loc[year]], axis=1, keys=["worker", "hour"]).dropna()
    ahead_hr = both_year[both_year["hour"] > 100].drop(BENCHMARK, errors="ignore")
    ahead_wk = both_year[both_year["worker"] > 100].drop(BENCHMARK, errors="ignore")
    print(f"\n{year}: of {len(both_year)} countries with hours data, {len(ahead_wk)} beat the US per worker and {len(ahead_hr)} per hour")
    print("ahead of the US per hour but not per worker:", ", ".join(names[i] for i in ahead_hr.index.difference(ahead_wk.index)))
    r = rel.loc[year].dropna().drop(BENCHMARK)
    print(f"\n{year}: {len(r)} economies besides the US; median = {r.median():.1f}% of US, share above 50% of US = {(r > 50).mean():.0%}")
    print(f"Highest: {', '.join(f'{names[i]} {v:.0f}' for i, v in r.nlargest(5).items())}")
    print(f"Lowest: {', '.join(f'{names[i]} {v:.1f}' for i, v in r.nsmallest(3).items())}")

    # --- growth over a window
    start, end = 2000, 2019
    g = window_cagr(pe, start, end).dropna()
    print(f"\n== GDP per person employed, CAGR {start}-{end} (%): {len(g)} economies ==")
    print(f"median {g.median():.2f}, US {g.get(BENCHMARK, float('nan')):.2f}")
    print("fastest:", ", ".join(f"{names[i]} {v:.1f}" for i, v in g.nlargest(5).items()))
    print("slowest:", ", ".join(f"{names[i]} {v:.1f}" for i, v in g.nsmallest(5).items()))
    conv = rel.loc[start].dropna().drop(BENCHMARK)
    both = pd.concat([np.log(conv), g.drop(BENCHMARK, errors="ignore")], axis=1, keys=["log_rel_start", "cagr"]).dropna()
    print(f"correlation of log(level relative to US in {start}) with growth {start}-{end}: {both.corr().iloc[0, 1]:.2f} (n={len(both)})")

    # --- sector gaps
    st = sector_table(wide, 2019)
    print(f"\n== Sector productivity gaps, 2019: {len(st)} economies ==")
    print(f"median services/agriculture ratio {st['srv_to_agr'].median():.1f}, industry/agriculture {st['ind_to_agr'].median():.1f}, APG {st['apg'].median():.1f}")
    print(f"share of economies where agriculture is the lowest-productivity sector: {(st[['va_agr','va_ind','va_srv']].idxmin(axis=1) == 'va_agr').mean():.0%}")
    st = add_metadata(st)
    inc = st.groupby("income_group")[["apg", "e_agr"]].median()
    print("by income group (median APG, agriculture employment share):")
    print(inc.to_string(float_format=lambda v: f"{v:.2f}"))
    chk = pd.concat([np.log(st["agg"]), np.log(pe.loc[2019].reindex(st.index))], axis=1, keys=["sector", "headline"]).dropna()
    print(f"sector-built aggregate (2015 US$) vs headline per-worker (2021 PPP$): correlation of logs {chk.corr().iloc[0, 1]:.3f} (n={len(chk)})")

    # --- shift-share
    ss = add_metadata(shift_share_window(wide, start, end))
    print(f"\n== Shift-share {start}-{end}: {len(ss)} economies with complete data ==")
    check = (ss[["within_pp", "between_pp", "interaction_pp"]].sum(axis=1) - ss["growth_pct"]).abs().max()
    print(f"max |within + between + interaction - total| = {check:.2e} pp")
    show = ss.loc[["CHN", "IND", "BRA", "NGA", "ETH", "DEU", "KOR", "VNM"]].copy()
    show.index = [names[i] for i in show.index]
    print(_fmt(show[["growth_pct", "within_pp", "between_pp", "interaction_pp"]]))
    print(f"share of economies where between-sector change was positive: {(ss['between_pp'] > 0).mean():.0%}")
    print(f"median contribution (pp): within {ss['within_pp'].median():.1f}, between {ss['between_pp'].median():.1f}, interaction {ss['interaction_pp'].median():.1f}")
    print("\nMedian by region (pp of growth):")
    print(summarise_by(ss, "region", ["growth_pct", "within_pp", "between_pp", "interaction_pp"]).to_string(float_format=lambda v: f"{v:.1f}"))
    print("\nMedian by income group (pp of growth):")
    print(summarise_by(ss, "income_group", ["growth_pct", "within_pp", "between_pp", "interaction_pp"]).to_string(float_format=lambda v: f"{v:.1f}"))

    # --- US per hour vs per worker
    pw = window_cagr(pe[[BENCHMARK]], 1991, 2023)[BENCHMARK]
    ph = window_cagr(hr[[BENCHMARK]], 1991, 2023)[BENCHMARK]
    oph = (us_oph.loc[2023] / us_oph.loc[1991]) ** (1 / 32) * 100 - 100
    print("\n== United States, 1991-2023 ==")
    print(f"GDP per person employed CAGR {pw:.2f}%; GDP per hour (WB/PWT estimate) {ph:.2f}%; nonfarm business output per hour (OPHNFB) {oph:.2f}%")
    print(f"US hours per engaged person: {hours.loc[1991, BENCHMARK]:.0f} in 1991, {hours.loc[2023, BENCHMARK]:.0f} in 2023")


if __name__ == "__main__":
    main()
