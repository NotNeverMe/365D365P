"""Central-bank policy rates against inflation and growth.

Sources
-------
* US: FRED ``FEDFUNDS`` (policy rate), ``CPIAUCSL`` (CPI), ``GDPC1`` / ``GDPPOT`` (real GDP and CBO potential).
* Other economies: BIS central-bank policy rates (``WS_CBPOL``, end of month) and BIS long consumer-price
  series (``WS_LONG_CPI``, year-on-year %), downloaded once and cached under ``data/bis/``.
* Euro area: the BIS series (ECB main refinancing rate, deposit facility rate from Sept 2024). FRED ``ECBDFR``
  (deposit facility rate) is available as an alternative: it sat about 1 point below the main rate before 2009.
* Growth for non-US economies: World Bank ``NY.GDP.MKTP.KD.ZG`` (annual).

All monthly series use a month-start ``DatetimeIndex`` and are in per cent.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import fred, worldbank
from core.http import get
from core.paths import DATA

BIS_DIR = DATA / "bis"
BIS_API = "https://stats.bis.org/api/v1/data"


@dataclass(frozen=True)
class Area:
    code: str  # BIS reference area
    name: str
    iso3: str  # World Bank code, for annual growth


AREAS: dict[str, Area] = {
    a.code: a
    for a in [
        Area("US", "United States", "USA"),
        Area("XM", "Euro area", "EMU"),
        Area("GB", "United Kingdom", "GBR"),
        Area("JP", "Japan", "JPN"),
        Area("CA", "Canada", "CAN"),
        Area("CH", "Switzerland", "CHE"),
        Area("AU", "Australia", "AUS"),
        Area("SE", "Sweden", "SWE"),
        Area("KR", "South Korea", "KOR"),
        Area("IN", "India", "IND"),
        Area("BR", "Brazil", "BRA"),
        Area("MX", "Mexico", "MEX"),
        Area("ZA", "South Africa", "ZAF"),
        Area("TR", "Turkey", "TUR"),
    ]
}


# --------------------------------------------------------------------------- loaders


def _download_bis(dataflow: str, key: str) -> pd.DataFrame:
    """One BIS SDMX request, reduced to tidy (area, date, value)."""
    text = get(f"{BIS_API}/{dataflow}/{key}", params={"format": "csv"}, timeout=120).text
    raw = pd.read_csv(io.StringIO(text), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])
    out = pd.DataFrame(
        {
            "area": raw["REF_AREA"],
            "date": pd.to_datetime(raw["TIME_PERIOD"], format="%Y-%m"),
            "value": pd.to_numeric(raw["OBS_VALUE"], errors="coerce"),
        }
    ).dropna()
    return out.sort_values(["area", "date"]).reset_index(drop=True)


def _bis_monthly(name: str, dataflow: str, key_suffix: str, *, refresh: bool = False) -> pd.DataFrame:
    path = BIS_DIR / f"{name}.csv.gz"
    if path.exists() and not refresh:
        return pd.read_csv(path, parse_dates=["date"])
    codes = "+".join(AREAS)
    frame = _download_bis(dataflow, f"M.{codes}{key_suffix}")
    BIS_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    return frame


def _bis_series(frame: pd.DataFrame, area: str, name: str) -> pd.Series:
    sub = frame[frame["area"] == area].set_index("date")["value"].sort_index()
    sub.name = name
    return sub


def ecb_deposit_rate(*, refresh: bool = False) -> pd.Series:
    """ECB deposit facility rate (FRED ``ECBDFR``, daily) averaged to months."""
    return fred.series("ECBDFR", refresh=refresh).resample("MS").mean().rename("policy_rate")


def policy_rate(area: str, *, ecb_deposit: bool = False, refresh: bool = False) -> pd.Series:
    """Monthly policy rate, per cent.

    US: effective federal funds rate (monthly average). Others: BIS end-of-month policy rate.
    ``ecb_deposit=True`` swaps the euro area for the ECB deposit facility rate.
    """
    if area == "US":
        return fred.series("FEDFUNDS", refresh=refresh).rename("policy_rate")
    if area == "XM" and ecb_deposit:
        return ecb_deposit_rate(refresh=refresh)
    return _bis_series(_bis_monthly("cbpol_monthly", "WS_CBPOL", "", refresh=refresh), area, "policy_rate")


def us_inflation(series_id: str = "CPIAUCSL") -> pd.Series:
    """US year-on-year inflation from a FRED price index (``CPIAUCSL`` headline, ``CPILFESL`` core)."""
    return yoy(fred.series(series_id)).rename("inflation")


def inflation(area: str, *, refresh: bool = False) -> pd.Series:
    """Monthly year-on-year consumer-price inflation, per cent (US from FRED CPIAUCSL, others BIS)."""
    if area == "US":
        return us_inflation()
    frame = _bis_monthly("cpi_yoy_monthly", "WS_LONG_CPI", ".771", refresh=refresh)
    return _bis_series(frame, area, "inflation")


def growth_annual(area: str) -> pd.Series:
    """Annual real GDP growth, per cent, indexed by calendar year (World Bank)."""
    wb = worldbank.indicator("NY.GDP.MKTP.KD.ZG")
    sub = wb[wb["iso3"] == AREAS[area].iso3].set_index("year")["value"].sort_index()
    sub.name = "growth"
    return sub


def us_growth_quarterly() -> pd.Series:
    """US real GDP growth over four quarters (year-on-year), per cent, quarter-start index."""
    return yoy(fred.series("GDPC1"), periods=4, freq="QS").rename("growth")


# ----------------------------------------------------------------------- calculations


def yoy(level: pd.Series, periods: int = 12, freq: str = "MS") -> pd.Series:
    """Percentage change against the same period one year earlier.

    The series is first placed on a complete calendar (``freq`` "MS" monthly, "QS" quarterly) so a
    missing observation (CPIAUCSL has no 2025-10) yields a gap, not a mis-aligned comparison.
    """
    full = level.asfreq(freq)
    return ((full / full.shift(periods) - 1.0) * 100.0).dropna()


def real_rate(nominal: pd.Series, inflation_yoy: pd.Series) -> pd.Series:
    """Ex-post real policy rate: nominal rate minus year-on-year inflation, months where both exist."""
    both = pd.concat([nominal, inflation_yoy], axis=1, join="inner").dropna()
    return (both.iloc[:, 0] - both.iloc[:, 1]).rename("real_rate")


def negative_spells(real: pd.Series) -> pd.DataFrame:
    """Runs of consecutive months with a negative real rate.

    Columns: start, end, months, mean_real, lowest_real, lowest_date.
    """
    real = real.dropna().sort_index()
    if real.empty:
        return pd.DataFrame(columns=["start", "end", "months", "mean_real", "lowest_real", "lowest_date"])
    # A new run starts when the sign flips or a calendar month is missing.
    negative = real < 0
    gap = real.index.to_series().diff() > pd.Timedelta(days=31)
    run_id = (negative.ne(negative.shift()) | gap).cumsum()
    rows = []
    for _, run in real[negative].groupby(run_id[negative]):
        rows.append(
            {
                "start": run.index[0],
                "end": run.index[-1],
                "months": len(run),
                "mean_real": run.mean(),
                "lowest_real": run.min(),
                "lowest_date": run.idxmin(),
            }
        )
    return pd.DataFrame(rows, columns=["start", "end", "months", "mean_real", "lowest_real", "lowest_date"])


def swing_points(rate: pd.Series, threshold: float = 1.5) -> pd.DataFrame:
    """Turning points of a rate series with a zig-zag filter.

    A peak (trough) is confirmed once the rate has fallen (risen) by at least ``threshold``
    percentage points from the running extreme. Columns: date, rate, kind ("peak" or "trough"),
    confirmed (False for the last extreme, which a later move could still replace).
    """
    s = rate.dropna()
    if s.empty:
        return pd.DataFrame(columns=["date", "rate", "kind", "confirmed"])
    hi = lo = (s.index[0], float(s.iloc[0]))
    direction = 0  # +1 rising from a trough, -1 falling from a peak, 0 undecided
    pivots: list[tuple[pd.Timestamp, float, str]] = []
    for date, value in s.items():
        value = float(value)
        if direction == 0:
            if value > hi[1]:
                hi = (date, value)
            if value < lo[1]:
                lo = (date, value)
            if value - lo[1] >= threshold:
                pivots.append((*lo, "trough"))
                direction, hi = 1, (date, value)
            elif hi[1] - value >= threshold:
                pivots.append((*hi, "peak"))
                direction, lo = -1, (date, value)
        elif direction == 1:
            if value > hi[1]:
                hi = (date, value)
            elif hi[1] - value >= threshold:
                pivots.append((*hi, "peak"))
                direction, lo = -1, (date, value)
        else:
            if value < lo[1]:
                lo = (date, value)
            elif value - lo[1] >= threshold:
                pivots.append((*lo, "trough"))
                direction, hi = 1, (date, value)
    if direction == 1:
        pivots.append((*hi, "peak"))
    elif direction == -1:
        pivots.append((*lo, "trough"))
    out = pd.DataFrame(pivots, columns=["date", "rate", "kind"])
    out["confirmed"] = True
    if not out.empty:
        out.loc[out.index[-1], "confirmed"] = False
    return out


def _months_between(start: pd.Timestamp, end: pd.Timestamp) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def hiking_cycles(rate: pd.Series, threshold: float = 1.5, liftoff_pp: float = 0.25) -> pd.DataFrame:
    """Each rise from a trough to the next peak, with the cut that followed.

    Columns: trough_date, trough_rate, liftoff_date, peak_date, peak_rate, rise_pp, months_liftoff_to_peak,
    next_trough_date, next_trough_rate, cut_pp, cut_complete.

    * ``liftoff_date`` is the first month the rate is at least ``liftoff_pp`` above the trough rate. It matters
      when the rate sits on a floor for years (US 2020-22): the trough is dated at the start of the floor,
      the lift-off at the first real increase.
    * The "next trough" is the lowest rate since the peak; ``cut_complete`` is False while a lower low could
      still follow (the latest cycle). A rise with no cut yet has NaN cut columns.
    """
    s = rate.dropna()
    pts = swing_points(s, threshold).reset_index(drop=True)
    rows = []
    for i in range(len(pts) - 1):
        if pts.at[i, "kind"] != "trough" or pts.at[i + 1, "kind"] != "peak":
            continue
        trough, peak = pts.loc[i], pts.loc[i + 1]
        nxt = pts.loc[i + 2] if i + 2 < len(pts) else None
        window = s.loc[trough["date"] : peak["date"]]
        liftoff = window[window >= trough["rate"] + liftoff_pp].index[0]
        rows.append(
            {
                "trough_date": trough["date"],
                "trough_rate": trough["rate"],
                "liftoff_date": liftoff,
                "peak_date": peak["date"],
                "peak_rate": peak["rate"],
                "rise_pp": peak["rate"] - trough["rate"],
                "months_liftoff_to_peak": _months_between(liftoff, peak["date"]),
                "next_trough_date": nxt["date"] if nxt is not None else pd.NaT,
                "next_trough_rate": nxt["rate"] if nxt is not None else np.nan,
                "cut_pp": peak["rate"] - nxt["rate"] if nxt is not None else np.nan,
                "cut_complete": bool(nxt is not None and nxt["confirmed"]),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ Taylor rule


def output_gap(gdp: pd.Series, potential: pd.Series) -> pd.Series:
    """Output gap in per cent of potential: 100 * (GDP - potential) / potential."""
    both = pd.concat([gdp, potential], axis=1, join="inner").dropna()
    return (100.0 * (both.iloc[:, 0] - both.iloc[:, 1]) / both.iloc[:, 1]).rename("output_gap")


def taylor_rate(
    inflation_yoy: pd.Series,
    gap: pd.Series,
    *,
    r_star: float = 2.0,
    pi_star: float = 2.0,
    w_pi: float = 0.5,
    w_gap: float = 0.5,
) -> pd.Series:
    """Taylor (1993) rule: i = r* + pi + w_pi * (pi - pi*) + w_gap * gap."""
    both = pd.concat([inflation_yoy, gap], axis=1, join="inner").dropna()
    pi, y = both.iloc[:, 0], both.iloc[:, 1]
    return (r_star + pi + w_pi * (pi - pi_star) + w_gap * y).rename("taylor")


def quarterly_mean(monthly: pd.Series) -> pd.Series:
    """Average of months within each calendar quarter, keeping only quarters with all three months."""
    grouped = monthly.resample("QS")
    return grouped.mean()[grouped.count() == 3]


def us_taylor_frame(*, r_star: float = 2.0, pi_star: float = 2.0, inflation_id: str = "CPIAUCSL") -> pd.DataFrame:
    """Quarterly US actual funds rate against the Taylor rule.

    Columns: actual, inflation, output_gap, taylor, gap_pp (= actual - taylor; negative means policy
    was looser than the rule). Potential GDP (CBO projection) is cut off at the last published GDP quarter.
    ``inflation_id`` picks the price index: ``CPIAUCSL`` (headline) or ``CPILFESL`` (core).
    """
    gdp = fred.series("GDPC1")
    potential = fred.series("GDPPOT").loc[: gdp.index[-1]]
    gap = output_gap(gdp, potential)
    infl_q = quarterly_mean(us_inflation(inflation_id))
    actual_q = quarterly_mean(policy_rate("US"))
    frame = pd.concat(
        {"actual": actual_q, "inflation": infl_q, "output_gap": gap}, axis=1, join="inner"
    ).dropna()
    frame["taylor"] = taylor_rate(frame["inflation"], frame["output_gap"], r_star=r_star, pi_star=pi_star)
    frame["gap_pp"] = frame["actual"] - frame["taylor"]
    return frame


def taylor_period_summary(frame: pd.DataFrame, periods: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """Average actual rate, rule rate and gap over named periods (inclusive, e.g. ``("2002-01", "2005-12")``)."""
    rows = []
    for label, (start, end) in periods.items():
        sub = frame.loc[start:end]
        rows.append(
            {
                "period": label,
                "quarters": len(sub),
                "actual": sub["actual"].mean(),
                "taylor": sub["taylor"].mean(),
                "gap_pp": sub["gap_pp"].mean(),
                "share_below_rule": (sub["gap_pp"] < 0).mean(),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ assembly


def economy_monthly(area: str, *, ecb_deposit: bool = False) -> pd.DataFrame:
    """Policy rate, inflation and real rate for one economy, by month."""
    rate, infl = policy_rate(area, ecb_deposit=ecb_deposit), inflation(area)
    out = pd.concat([rate, infl], axis=1, join="inner").dropna()
    out["real_rate"] = out["policy_rate"] - out["inflation"]
    return out


def coverage() -> pd.DataFrame:
    """Data coverage and negative-real-rate summary per economy."""
    rows = []
    for code, area in AREAS.items():
        rate, infl = policy_rate(code), inflation(code)
        both = economy_monthly(code)
        recent = both.loc["2000-01-01":, "real_rate"]
        rows.append(
            {
                "economy": area.name,
                "rate_first": rate.index[0],
                "rate_last": rate.index[-1],
                "inflation_first": infl.index[0],
                "inflation_last": infl.index[-1],
                "months_with_both": len(both),
                "negative_real_months": int((both["real_rate"] < 0).sum()),
                "lowest_real_since_2000": recent.min(),
                "lowest_date": recent.idxmin(),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------- main


def format_table(frame: pd.DataFrame, digits: int = 2) -> pd.DataFrame:
    """Display copy of a table: dates as YYYY-MM, floats rounded."""
    out = frame.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m")
        elif pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(digits)
    return out


def main() -> None:
    cov = coverage()
    cov["share_negative"] = cov["negative_real_months"] / cov["months_with_both"]
    print("== Coverage (monthly policy rate, inflation) ==")
    print(format_table(cov, 3).to_string(index=False))

    us = economy_monthly("US")
    n_neg = int((us["real_rate"] < 0).sum())
    print("\n== US real policy rate (FEDFUNDS - CPIAUCSL year-on-year) ==")
    print(f"Months with both: {len(us)} ({us.index[0]:%Y-%m} to {us.index[-1]:%Y-%m})")
    print(f"Negative real-rate months: {n_neg} ({n_neg / len(us):.1%})")
    last = us.iloc[-1]
    print(f"Latest ({us.index[-1]:%Y-%m}): policy {last['policy_rate']:.2f}, inflation {last['inflation']:.2f}, real {last['real_rate']:.2f}")
    print("Longest negative spells:")
    print(format_table(negative_spells(us["real_rate"]).sort_values("months", ascending=False).head(6)).to_string(index=False))

    xm_main, xm_dfr = economy_monthly("XM"), economy_monthly("XM", ecb_deposit=True)
    print("\n== Euro area: negative real-rate months by policy-rate definition ==")
    print(f"BIS (main refinancing rate, deposit rate since 2024-09): {(xm_main['real_rate'] < 0).sum()} of {len(xm_main)}")
    print(f"FRED ECBDFR (deposit facility rate): {(xm_dfr['real_rate'] < 0).sum()} of {len(xm_dfr)}")

    print("\n== US hiking cycles (zig-zag threshold 1.5pp on FEDFUNDS) ==")
    print(format_table(hiking_cycles(policy_rate("US"))).to_string(index=False))

    print("\n== US Taylor rule (r*=2, pi*=2, output gap = GDPC1 vs CBO potential GDPPOT) ==")
    periods = {
        "1987-2001": ("1987-01", "2001-12"),
        "2002-2005": ("2002-01", "2005-12"),
        "2009-2015": ("2009-01", "2015-12"),
        "2021-2022": ("2021-01", "2022-12"),
        "2023-latest": ("2023-01", "2100-01"),
    }
    for label, series_id in [("headline CPI (CPIAUCSL)", "CPIAUCSL"), ("core CPI (CPILFESL)", "CPILFESL")]:
        taylor = us_taylor_frame(inflation_id=series_id)
        print(f"-- inflation measure: {label}; quarters {len(taylor)} ({taylor.index[0]:%Y-%m} to {taylor.index[-1]:%Y-%m})")
        print(format_table(taylor_period_summary(taylor, periods)).to_string(index=False))
        latest = taylor.iloc[-1]
        print(f"Latest quarter {taylor.index[-1]:%Y-%m}: actual {latest['actual']:.2f}, rule {latest['taylor']:.2f}, gap {latest['gap_pp']:.2f}pp")
        print(f"Most below rule: {taylor['gap_pp'].idxmin():%Y-%m} ({taylor['gap_pp'].min():.2f}pp); most above: {taylor['gap_pp'].idxmax():%Y-%m} ({taylor['gap_pp'].max():.2f}pp)")
        zlb = taylor.loc["2009-01-01":"2015-12-31"]
        print(f"Quarters 2009-2015 in which the rule itself is below zero: {(zlb['taylor'] < 0).sum()} of {len(zlb)}")


if __name__ == "__main__":
    main()
