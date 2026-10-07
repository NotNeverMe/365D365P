"""Do wages keep pace with inflation? US wage series against CPI-U, plus a cross-country panel.

Core quantities: real wage (nominal wage divided by CPI), cumulative real change from a base
month, the share of months with falling real wages, episodes in which prices outran wages,
decade summaries, and the lead/lag cross-correlation between inflation and wage growth.

Pure functions on pandas objects; Streamlit lives in ``app.py``. Data come from FRED
(``core.fred``) and, for the price side of the cross-country panel, the World Bank.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import ccf

from core import fred
from core import worldbank as wb

CPI = "CPIAUCSL"  # CPI-U, all items, seasonally adjusted, 1982-84 = 100

WAGE_SERIES = {
    "AHETPI": "Average hourly earnings, production and nonsupervisory employees (monthly, from 1964)",
    "CES0500000003": "Average hourly earnings, all private employees (monthly, from 2006)",
    "LEU0252881500Q": "Median usual weekly earnings, full-time workers (quarterly, from 1979)",
}
BLS_REAL_MEDIAN = "LES1252881600Q"  # BLS's own real version of the median weekly earnings series

GROWTH_KINDS = {
    "12m": "12-month change",
    "3m": "3-month change",
    "1m": "month-over-month change",
    "12m_diff": "monthly change in the 12-month rate",
}

# OECD "Hourly earnings: manufacturing" (index, 2015 = 100) republished on FRED. For each country this is
# the variant with the latest last observation among LCEAMN01<ISO2>{M,Q}661{S,N}. None = no series found.
PANEL_WAGE_IDS: dict[str, str | None] = {
    "USA": "LCEAMN01USM661N", "GBR": "LCEAMN01GBM661S", "DEU": "LCEAMN01DEQ661N", "FRA": "LCEAMN01FRQ661S",
    "ITA": "LCEAMN01ITM661S", "JPN": "LCEAMN01JPM661S", "CAN": "LCEAMN01CAM661N", "AUS": "LCEAMN01AUQ661S",
    "ESP": "LCEAMN01ESQ661S", "NLD": "LCEAMN01NLM661S", "SWE": "LCEAMN01SEM661N", "NOR": "LCEAMN01NOQ661N",
    "DNK": "LCEAMN01DKQ661N", "KOR": "LCEAMN01KRQ661S", "MEX": "LCEAMN01MXM661S", "BEL": "LCEAMN01BEQ661S",
    "AUT": "LCEAMN01ATM661S", "FIN": "LCEAMN01FIQ661N", "IRL": "LCEAMN01IEQ661N", "PRT": "LCEAMN01PTM661N",
    "POL": "LCEAMN01PLM661S", "NZL": "LCEAMN01NZQ661N", "CZE": "LCEAMN01CZQ661S", "HUN": "LCEAMN01HUM661S",
    "SVK": "LCEAMN01SKM661S", "SVN": "LCEAMN01SIM661N", "LUX": "LCEAMN01LUM661N", "ISR": "LCEAMN01ILM661N",
    "EST": "LCEAMN01EEQ661S", "ISL": "LCEAMN01ISQ661N", "TUR": "LCEAMN01TRQ661N",
    "CHE": None, "GRC": None, "LVA": None, "LTU": None, "CHL": None, "COL": None, "CRI": None,
}  # fmt: skip
QUARTERLY_CPI_ONLY = {"AUS", "NZL"}  # the OECD publishes no monthly CPI growth series for these on FRED
BRIEF_WAGE_IDS = ["LCEAMN01USM189S", "LCEAMN01CAM189S"]  # the ...M189S form: the only two countries where it exists
NO_SERIES_REASON = "no OECD hourly-earnings series on FRED (checked monthly and quarterly, S and N variants)"
WB_INFLATION = "FP.CPI.TOTL.ZG"  # CPI inflation, annual average, %


# ------------------------------------------------------------------------------------ loading and alignment


def load_us() -> pd.DataFrame:
    """CPI and the three US wage series side by side (monthly or quarterly dates, NaN where not published)."""
    ids = {"cpi": CPI, **{sid: sid for sid in WAGE_SERIES}}
    return pd.concat({name: fred.series(sid) for name, sid in ids.items()}, axis=1, sort=True)


def periods_per_year(index: pd.DatetimeIndex) -> int:
    """12 for monthly data, 4 for quarterly, judged from the median spacing between dates."""
    spacing = pd.Series(index).diff().dt.days.median()
    return 12 if spacing < 45 else 4


def aligned(wage: pd.Series, cpi: pd.Series) -> pd.DataFrame:
    """Wage and CPI on the wage series' own dates, first and last common date only.

    A quarterly wage series is paired with the average CPI of the same three months (quarters
    with fewer than three CPI readings are dropped), which is how BLS deflates its quarterly series.
    """
    wage, cpi = wage.dropna(), cpi.dropna()
    if periods_per_year(wage.index) == 4:
        q = cpi.resample("QS").agg(["mean", "count"])
        cpi = q.loc[q["count"] == 3, "mean"]
    return pd.concat({"wage": wage, "cpi": cpi}, axis=1, sort=True).dropna()


# ------------------------------------------------------------------------------------ real wages


def real_wage(df: pd.DataFrame) -> pd.Series:
    """Nominal wage deflated by CPI, in dollars of the CPI base period (1982-84 = 100 for CPIAUCSL)."""
    return (df["wage"] / df["cpi"] * 100.0).rename("real_wage")


def cumulative_real_change(real: pd.Series, base: str | pd.Timestamp) -> pd.Series:
    """Percent change of the real wage since ``base`` (the first observation on or after that date)."""
    tail = real.loc[pd.Timestamp(base) :]
    if tail.empty:
        raise ValueError("base date is after the last observation")
    return ((tail / tail.iloc[0] - 1.0) * 100.0).rename("cumulative_real_change_pct")


def regular(series: pd.Series, ppy: int) -> pd.Series:
    """Put a series on a gap-free monthly (``ppy`` = 12) or quarterly grid; missing periods become NaN.

    Growth over "12 months" must mean twelve calendar months, not twelve rows. FRED has holes
    (the US CPI has no October 2025 reading), and counting rows would silently shift every later
    comparison by a month.
    """
    return series.asfreq("MS" if ppy == 12 else "QS")


def growth(series: pd.Series, kind: str, ppy: int = 12) -> pd.Series:
    """Percent change over a calendar horizon. ``kind``: '12m' (year on year), '3m', '1m', '12m_diff'.

    '12m_diff' is the one-period change in the 12-month rate (in percentage points). For quarterly
    data (``ppy`` = 4) '3m' and '1m' are both one quarter. Gaps in the data give NaN, never a
    comparison with the wrong date.
    """
    s = regular(series, ppy)
    if kind == "12m":
        return s.pct_change(ppy, fill_method=None) * 100.0
    if kind == "3m":
        return s.pct_change(max(ppy // 4, 1), fill_method=None) * 100.0
    if kind == "1m":
        return s.pct_change(1, fill_method=None) * 100.0
    if kind == "12m_diff":
        return (s.pct_change(ppy, fill_method=None) * 100.0).diff()
    raise ValueError(f"unknown growth kind {kind!r}")


def real_growth(df: pd.DataFrame, kind: str = "12m") -> pd.Series:
    """Real wage growth (%) over the chosen horizon: (1 + nominal) / (1 + inflation) - 1."""
    ppy = periods_per_year(df.index)
    w, p = growth(df["wage"], kind, ppy), growth(df["cpi"], kind, ppy)
    if kind == "12m_diff":
        return (w - p).rename("real_growth_pct")
    return (((1 + w / 100.0) / (1 + p / 100.0) - 1.0) * 100.0).rename("real_growth_pct")


def negative_share(growth_rates: pd.Series) -> float:
    """Share of observations (with a growth rate) where growth was below zero."""
    g = growth_rates.dropna()
    return float((g < 0).mean()) if len(g) else float("nan")


# ------------------------------------------------------------------------------------ episodes and decades


def gap_episodes(df: pd.DataFrame, min_periods: int = 6) -> pd.DataFrame:
    """Runs of consecutive periods in which 12-month inflation exceeded 12-month wage growth.

    ``gap_pp`` = inflation - wage growth, in percentage points. Runs shorter than ``min_periods``
    observations are ignored. Columns: start, end, periods, mean_gap_pp, peak_gap_pp, peak_date,
    inflation_at_peak, wage_growth_at_peak.
    """
    ppy = periods_per_year(df.index)
    infl, wage = growth(df["cpi"], "12m", ppy), growth(df["wage"], "12m", ppy)
    gap = infl - wage  # NaN where a month is missing, so a run cannot jump across a hole
    outran = gap.gt(0)
    run_id = (outran != outran.shift()).cumsum()
    rows = []
    for _, run in gap[outran].groupby(run_id[outran]):
        if len(run) < min_periods:
            continue
        peak = run.idxmax()
        rows.append(
            {
                "start": run.index[0],
                "end": run.index[-1],
                "periods": len(run),
                "mean_gap_pp": run.mean(),
                "peak_gap_pp": run.max(),
                "peak_date": peak,
                "inflation_at_peak": infl[peak],
                "wage_growth_at_peak": wage[peak],
            }
        )
    cols = ["start", "end", "periods", "mean_gap_pp", "peak_gap_pp", "peak_date", "inflation_at_peak", "wage_growth_at_peak"]
    return pd.DataFrame(rows, columns=cols)


def annual_table(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar-year figures from annual averages (complete years only).

    Columns: wage_growth_pct, inflation_pct, real_growth_pct, gap_pp (inflation minus wage growth).
    """
    ppy = periods_per_year(df.index)
    g = df.groupby(df.index.year)
    means = g.mean()[g.size() == ppy]
    means = means.reindex(range(means.index.min(), means.index.max() + 1))  # a missing year must not be skipped over
    out = pd.DataFrame(
        {
            "wage_growth_pct": means["wage"].pct_change(fill_method=None) * 100.0,
            "inflation_pct": means["cpi"].pct_change(fill_method=None) * 100.0,
        }
    ).dropna()
    out["real_growth_pct"] = ((1 + out["wage_growth_pct"] / 100) / (1 + out["inflation_pct"] / 100) - 1) * 100.0
    out["gap_pp"] = out["inflation_pct"] - out["wage_growth_pct"]
    out.index.name = "year"
    return out


def decade_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per decade: compound annual inflation, wage growth and real wage growth, and share of falling real wages.

    A decade runs from the last observation of the previous decade (or the first observation we
    have) to its own last observation, so a decade is ten years of change where the data allow.
    Rates are compound annual rates between the end points, not averages of annual rates.
    """
    ppy = periods_per_year(df.index)
    real = df["wage"] / df["cpi"]
    yoy_real = real_growth(df, "12m")
    rows = []
    for decade in sorted({(y // 10) * 10 for y in df.index.year}):
        in_decade = df.index[(df.index.year // 10) * 10 == decade]
        before = df.index[df.index < in_decade[0]]
        start = before[-1] if len(before) else in_decade[0]
        end = in_decade[-1]
        years = (end - start).days / 365.25
        if years < 1:
            continue
        rate = lambda s: ((s[end] / s[start]) ** (1 / years) - 1) * 100.0  # noqa: E731
        rows.append(
            {
                "decade": f"{decade}s",
                "from": start,
                "to": end,
                "years": years,
                "inflation_pct": rate(df["cpi"]),
                "wage_growth_pct": rate(df["wage"]),
                "real_wage_growth_pct": rate(real),
                "share_falling_real_wage": negative_share(yoy_real.loc[in_decade]),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------ lead / lag


def longest_unbroken(frame: pd.DataFrame) -> pd.DataFrame:
    """The longest stretch of consecutive, fully observed periods (``frame`` on a regular grid, NaN = missing)."""
    ok = frame.notna().all(axis=1)
    run_id = (ok != ok.shift()).cumsum()
    sizes = ok.groupby(run_id).sum()
    best = sizes.idxmax()
    return frame[(run_id == best) & ok]


def cross_correlation(inflation: pd.Series, wage_growth: pd.Series, max_lag: int = 36) -> pd.Series:
    """Cross-correlation of wage growth and inflation at lags -max_lag .. +max_lag (``statsmodels.ccf``).

    The value at lag k is corr(wage growth at t+k, inflation at t). A peak at a positive k means
    wage growth *follows* inflation by k periods; a negative k means it comes first. ``ccf`` needs
    an unbroken series, so the longest stretch with both series observed in every period is used
    (this drops the months around a data hole such as the missing October 2025 CPI).
    """
    z = pd.concat({"infl": inflation, "wage": wage_growth}, axis=1, sort=True)
    z = longest_unbroken(regular(z, periods_per_year(z.index)))
    if len(z) < 2 * max_lag:  # so that even the longest lag still uses at least half the sample
        raise ValueError(f"need at least {2 * max_lag} unbroken observations for max_lag={max_lag}, have {len(z)}")
    wage_after = ccf(z["wage"].to_numpy(), z["infl"].to_numpy(), adjusted=False)[: max_lag + 1]  # k >= 0
    infl_after = ccf(z["infl"].to_numpy(), z["wage"].to_numpy(), adjusted=False)[: max_lag + 1]  # k <= 0
    values = np.concatenate([infl_after[::-1][:-1], wage_after])
    return pd.Series(values, index=pd.RangeIndex(-max_lag, max_lag + 1, name="lag"), name="correlation")


def peak_lag(cc: pd.Series, tolerance: float = 0.02) -> dict:
    """Lag of the highest correlation, its value, the lag-0 value, and the contiguous lags within ``tolerance``."""
    lag = int(cc.idxmax())
    ok = cc >= cc.max() - tolerance
    lo = hi = lag
    while lo - 1 in ok.index and ok[lo - 1]:
        lo -= 1
    while hi + 1 in ok.index and ok[hi + 1]:
        hi += 1
    return {"lag": lag, "correlation": float(cc.max()), "lag0": float(cc[0]), "plateau": (lo, hi)}


# ------------------------------------------------------------------------------------ cross-country panel


def annual_means(series: pd.Series) -> pd.Series:
    """Annual average of a monthly or quarterly series, indexed by calendar year.

    Only complete years get a value; incomplete years (and any year in between with a hole) are NaN,
    so the index is contiguous and ``pct_change`` always compares neighbouring years.
    """
    ppy = periods_per_year(series.index)
    g = series.groupby(series.index.year)
    full = g.mean()[g.count() == ppy]
    return full.reindex(range(int(series.index.year.min()), int(series.index.year.max()) + 1)).rename_axis("year")


def load_panel_wages() -> dict[str, pd.Series]:
    """Raw OECD wage index series for every candidate that has one."""
    return {iso: fred.series(sid) for iso, sid in PANEL_WAGE_IDS.items() if sid}


def oecd_cpi_last_dates() -> pd.DataFrame:
    """Last observation of the OECD CPI-inflation series (``CPALTT01<ISO2>M659N``, % change on a year earlier).

    These are the series that would "match" the OECD wage series on FRED. Their last dates show why the
    panel takes prices from the World Bank instead (Australia and New Zealand: quarterly ``Q659N``).
    """
    rows = []
    for iso, wage_id in PANEL_WAGE_IDS.items():
        if wage_id is None:
            continue
        cpi_id = f"CPALTT01{wage_id[8:10]}{'Q' if iso in QUARTERLY_CPI_ONLY else 'M'}659N"
        rows.append({"iso3": iso, "cpi_series": cpi_id, "last_date": fred.series(cpi_id).index.max()})
    return pd.DataFrame(rows).set_index("iso3").sort_values("last_date")


def panel_inflation(us_cpi: pd.Series) -> pd.DataFrame:
    """Annual CPI inflation (%), rows = year, columns = iso3: World Bank, with the US from FRED CPI-U.

    The World Bank series has no US value for 2025, so the US uses annual averages of CPIAUCSL
    throughout, which keeps the US row consistent with the rest of the project.
    """
    infl = wb.indicator(WB_INFLATION).pivot(index="year", columns="iso3", values="value").sort_index()
    us = annual_means(us_cpi).pct_change(fill_method=None) * 100.0
    infl["USA"] = us.reindex(infl.index)
    return infl


def panel_status(wages: dict[str, pd.Series], inflation: pd.DataFrame, base_year: int, last_year: int) -> pd.DataFrame:
    """For every candidate country: last observation, and whether it is recent enough to include.

    Included only if the wage index has complete annual averages for every year from ``base_year``
    to ``last_year`` and the price series has inflation for every year after ``base_year``.
    """
    rows = []
    for iso, sid in PANEL_WAGE_IDS.items():
        row = {"iso3": iso, "wage_series": sid, "wage_last_date": pd.NaT, "included": False, "reason": ""}
        if sid is None:
            row["reason"] = NO_SERIES_REASON
        else:
            s = wages[iso]
            annual = annual_means(s)
            row["wage_last_date"] = s.index.max()
            needed = range(base_year, last_year + 1)
            missing_wage = [y for y in needed if pd.isna(annual.get(y))]
            infl = inflation[iso].reindex(range(base_year + 1, last_year + 1)) if iso in inflation else None
            if missing_wage:
                row["reason"] = f"wage index has no complete year {missing_wage[0]}" + ("" if len(missing_wage) == 1 else f" onward ({len(missing_wage)} years)") + f"; last observation {s.index.max():%Y-%m}"
            elif infl is None or infl.isna().any():
                gone = [] if infl is None else [int(y) for y in infl.index[infl.isna()]]
                row["reason"] = f"no complete CPI inflation for {', '.join(map(str, gone)) or 'the window'}"
            else:
                row["included"] = True
        rows.append(row)
    return pd.DataFrame(rows).set_index("iso3")


def panel_real_wages(wages: dict[str, pd.Series], inflation: pd.DataFrame, status: pd.DataFrame, base_year: int, last_year: int) -> pd.DataFrame:
    """Long frame of annual real wage growth for included countries.

    Columns: iso3, year, wage_growth_pct (annual average on annual average), inflation_pct,
    real_growth_pct = (1 + wage) / (1 + inflation) - 1, and cumulative_real_pct since ``base_year``.
    """
    rows = []
    for iso in status.index[status["included"]]:
        w = annual_means(wages[iso]).pct_change(fill_method=None) * 100.0
        for year in range(base_year + 1, last_year + 1):
            rows.append({"iso3": iso, "year": year, "wage_growth_pct": w[year], "inflation_pct": inflation.loc[year, iso]})
    out = pd.DataFrame(rows, columns=["iso3", "year", "wage_growth_pct", "inflation_pct"])
    out["real_growth_pct"] = ((1 + out["wage_growth_pct"] / 100) / (1 + out["inflation_pct"] / 100) - 1) * 100.0
    out["cumulative_real_pct"] = (
        out.groupby("iso3")["real_growth_pct"].transform(lambda r: ((1 + r / 100).cumprod() - 1) * 100.0)
    )
    return out


def panel_summary(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per country: cumulative real change to the last year, years with falling real wages, worst year."""
    g = panel.groupby("iso3")
    out = pd.DataFrame(
        {
            "cumulative_real_pct": g["cumulative_real_pct"].last(),
            "years": g.size().astype(int),
            "years_falling": g["real_growth_pct"].apply(lambda r: int((r < 0).sum())),
            "worst_real_growth_pct": g["real_growth_pct"].min(),
        }
    )
    out["worst_year"] = g.apply(lambda d: int(d.loc[d["real_growth_pct"].idxmin(), "year"]), include_groups=False)
    return out.sort_values("cumulative_real_pct")


# ------------------------------------------------------------------------------------ summary


def _gaps(name: str, s: pd.Series, freq: str) -> str:
    holes = pd.date_range(s.index.min(), s.index.max(), freq=freq).difference(s.index)
    return f"{name}: {', '.join(f'{d:%Y-%m}' for d in holes) or 'no gaps'}"


def main() -> None:
    us = load_us()
    print("== US series (FRED) ==")
    for col in us:
        s = us[col].dropna()
        print(f"{col:>15}: {s.index.min():%Y-%m} to {s.index.max():%Y-%m}  ({len(s)} obs)")
    cpi = us["cpi"].dropna()
    print("Missing periods inside the samples ->", _gaps("CPIAUCSL", cpi, "MS"), "|", _gaps("AHETPI", us["AHETPI"].dropna(), "MS"), "|", _gaps("LEU0252881500Q", us["LEU0252881500Q"].dropna(), "QS"))

    ahe = aligned(us["AHETPI"], cpi)
    ces = aligned(us["CES0500000003"], cpi)
    med = aligned(us["LEU0252881500Q"], cpi)
    print(f"\nAHETPI aligned with CPI: {ahe.index.min():%Y-%m} to {ahe.index.max():%Y-%m} ({len(ahe)} months)")

    bls = fred.series(BLS_REAL_MEDIAN)
    cmp_ = pd.concat([real_wage(med), bls], axis=1, keys=["mine", "bls"], sort=True).dropna()
    rel = (cmp_["mine"] / cmp_["bls"] - 1).abs() * 100
    print(f"Median weekly earnings: my CPI deflation vs BLS real series over {len(cmp_)} quarters: mean abs gap {rel.mean():.2f}%, max {rel.max():.2f}%")

    print("\n== Real wage (AHETPI / CPIAUCSL): cumulative change from a base month to the latest ==")
    real = real_wage(ahe)
    for base in ["1964-01-01", "1973-01-01", "1979-01-01", "2019-01-01", "2020-01-01", "2021-01-01", "2022-06-01"]:
        c = cumulative_real_change(real, base)
        print(f"from {c.index[0]:%Y-%m}: {c.iloc[-1]:+.1f}% (low {c.min():+.1f}% in {c.idxmin():%Y-%m}, high {c.max():+.1f}% in {c.idxmax():%Y-%m})")
    print(f"real wage peak: {real.idxmax():%Y-%m}, latest is {real.iloc[-1] / real.max() - 1:+.1%} from that peak")

    print("\n== Same base (2019-01 or 2019 Q1) across wage measures: real change to the latest observation ==")
    for label, df in [("AHETPI (production & nonsupervisory)", ahe), ("CES0500000003 (all private)", ces), ("Median weekly earnings (full-time)", med)]:
        c = cumulative_real_change(real_wage(df), "2019-01-01")
        print(f"{label:40s} {c.iloc[-1]:+.1f}% to {c.index[-1]:%Y-%m}")
    print(f"AHETPI real wage in 2020-04 vs 2020-02: {real.loc['2020-04-01'] / real.loc['2020-02-01'] - 1:+.1%} in two months (composition effect: low-paid jobs were lost first)")

    print("\n== Share of months with falling real wages ==")
    for label, df in [("AHETPI 1964-", ahe), ("AHETPI 1983-", ahe.loc["1983":]), ("CES0500000003 2006-", ces)]:
        r12 = real_growth(df, "12m")
        print(f"{label:22s} 12-month: {negative_share(r12):.1%}   month-over-month: {negative_share(real_growth(df, '1m')):.1%}   (n={r12.notna().sum()})")
    r12 = real_growth(med, "12m")
    print(f"Median weekly earnings (quarterly) 12-month: {negative_share(r12):.1%} of {r12.notna().sum()} quarters")

    print("\n== Episodes where 12-month inflation exceeded 12-month wage growth (AHETPI, >= 6 months) ==")
    ep = gap_episodes(ahe, 6)
    show = ep.assign(start=ep["start"].dt.strftime("%Y-%m"), end=ep["end"].dt.strftime("%Y-%m"), peak_date=ep["peak_date"].dt.strftime("%Y-%m"))
    print(show.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print(f"{len(ep)} episodes covering {ep['periods'].sum()} of {real_growth(ahe, '12m').notna().sum()} months with a 12-month rate")

    print("\n== Calendar years: inflation above wage growth (AHETPI annual averages) ==")
    at = annual_table(ahe)
    bad = at[at["gap_pp"] > 0]
    print(f"{len(bad)} of {len(at)} years ({at.index.min()}-{at.index.max()}): " + ", ".join(f"{y} ({g:+.1f}pp)" for y, g in bad["gap_pp"].items()))

    print("\n== Decades (compound annual rates, %) ==")
    print(decade_summary(ahe).to_string(index=False, float_format=lambda v: f"{v:.2f}", formatters={"from": lambda d: f"{d:%Y-%m}", "to": lambda d: f"{d:%Y-%m}"}))

    print("\n== Lead/lag: corr(wage growth at t+k, inflation at t), max lag 36 (24 where fewer than 72 unbroken months) (AHETPI) ==")
    for kind in ["12m", "3m", "1m", "12m_diff"]:
        infl, wg = growth(ahe["cpi"], kind), growth(ahe["wage"], kind)
        for label, a, b in [("1964-2026", "1964", "2026"), ("1964-1982", "1964", "1982"), ("1983-2019", "1983", "2019"), ("2020-2026", "2020", "2026")]:
            z = longest_unbroken(pd.concat({"i": infl.loc[a:b], "w": wg.loc[a:b]}, axis=1, sort=True))
            pk = peak_lag(cross_correlation(infl.loc[a:b], wg.loc[a:b], 36 if len(z) >= 72 else 24))
            print(f"{GROWTH_KINDS[kind][:24]:24s} {label:10s} n={len(z):3d} peak lag {pk['lag']:+3d}  r={pk['correlation']:.2f}  lag0 r={pk['lag0']:.2f}  within 0.02 of peak: lags {pk['plateau'][0]:+d}..{pk['plateau'][1]:+d}")

    print("\n== Cross-country panel: OECD hourly earnings in manufacturing vs CPI inflation (World Bank; US from FRED) ==")
    for sid in BRIEF_WAGE_IDS:
        t = fred.series(sid)
        print(f"{sid} (id form from the brief): {t.index.min():%Y-%m} to {t.index.max():%Y-%m}")
    wages = load_panel_wages()
    last = {iso: s.index.max() for iso, s in wages.items()}
    print(f"OECD wage index series (661 variants): {len(wages)} countries; last observation median {pd.Series(last).median():%Y-%m}, earliest {min(last.values()):%Y-%m}, latest {max(last.values()):%Y-%m}")
    oecd_cpi = oecd_cpi_last_dates()
    print(f"OECD matching CPI-growth series (CPALTT01..659N): {len(oecd_cpi)} series; last observation earliest {oecd_cpi['last_date'].min():%Y-%m}, median {oecd_cpi['last_date'].median():%Y-%m}, latest {oecd_cpi['last_date'].max():%Y-%m}; reaching 2025-12: {(oecd_cpi['last_date'] >= '2025-12-01').sum()}")
    print("ending before 2025:", ", ".join(f"{i} {d:%Y-%m}" for i, d in oecd_cpi['last_date'].items() if d < pd.Timestamp('2025-01-01')))
    infl = panel_inflation(cpi)
    n = wb.names()
    for base_year, last_year in ((2019, 2025), (2015, 2025), (2019, 2024)):
        status = panel_status(wages, infl, base_year, last_year)
        panel = panel_real_wages(wages, infl, status, base_year, last_year)
        summ = panel_summary(panel)
        print(f"\n-- base {base_year}, last full year {last_year}: {int(status['included'].sum())} of {len(status)} candidates included --")
        print(f"{(summ['cumulative_real_pct'] > 0).sum()} of {len(summ)} countries: real manufacturing earnings higher in {last_year} than in {base_year}; median change {summ['cumulative_real_pct'].median():+.1f}%")
        print("lowest:", "; ".join(f"{n[i]} {r['cumulative_real_pct']:+.1f}% ({int(r['years_falling'])}/{int(r['years'])} falling years)" for i, r in summ.head(5).iterrows()))
        print("highest:", "; ".join(f"{n[i]} {r['cumulative_real_pct']:+.1f}%" for i, r in summ.tail(3).iterrows()))
        if "USA" in summ.index:
            print(f"USA (OECD manufacturing series): {summ.loc['USA', 'cumulative_real_pct']:+.1f}%")
        if (base_year, last_year) == (2019, 2025):
            print("Dropped:")
            for iso, r in status[~status["included"]].iterrows():
                print(f"  {iso} {n.get(iso, iso)}: {r['reason']}")
            print("Included:", ", ".join(status.index[status["included"]]))
        else:
            print("Dropped:", "; ".join(f"{i}" for i in status.index[~status["included"]]))


if __name__ == "__main__":
    main()
