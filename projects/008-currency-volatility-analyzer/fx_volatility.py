"""Exchange-rate volatility, instability periods and worst depreciation episodes.

Data: FRED daily H.10 exchange rates (``DEX...``), loaded through ``core.fred``. Every series is
normalised to **US dollars per one unit of foreign currency**, so a fall always means the foreign
currency depreciated against the dollar and a rise means it appreciated.

Definitions used throughout
---------------------------
* log return: ``ln(rate_t) - ln(rate_{t-1})`` between consecutive observations of the same series.
* rolling volatility: standard deviation of the last ``window`` log returns, times ``sqrt(252)``, in per cent.
* instability flag: a day is *unstable* when rolling volatility is above a cut-off. The cut-off is either
  the series' own q-th percentile of rolling volatility over its whole history ("relative", default q = 0.90)
  or a fixed annualised level in per cent ("absolute").
* instability period: a run of unstable days, with runs less than ``merge_days`` calendar days apart merged.
* depreciation over h days: ``rate_t / rate_{t-h days} - 1`` using the last observation on or before the
  start date. The worst episodes are the most negative values, with overlapping windows removed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import fred, stats

TRADING_DAYS = 252
MAX_STALE_DAYS = 7  # a horizon window may start at most this many days earlier than asked (data gaps, holidays)


@dataclass(frozen=True)
class Currency:
    code: str
    name: str
    series_id: str
    usd_per_unit: bool  # True if FRED quotes USD per foreign unit (EUR, GBP); False if foreign units per USD


CURRENCIES: dict[str, Currency] = {
    c.code: c
    for c in [
        Currency("EUR", "Euro", "DEXUSEU", True),
        Currency("JPY", "Japanese yen", "DEXJPUS", False),
        Currency("GBP", "British pound", "DEXUSUK", True),
        Currency("INR", "Indian rupee", "DEXINUS", False),
        Currency("CNY", "Chinese yuan", "DEXCHUS", False),
        Currency("CAD", "Canadian dollar", "DEXCAUS", False),
        Currency("CHF", "Swiss franc", "DEXSZUS", False),
        Currency("BRL", "Brazilian real", "DEXBZUS", False),
        Currency("MXN", "Mexican peso", "DEXMXUS", False),
        Currency("KRW", "South Korean won", "DEXKOUS", False),
        Currency("ZAR", "South African rand", "DEXSFUS", False),
        Currency("THB", "Thai baht", "DEXTHUS", False),
    ]
}


# --------------------------------------------------------------------------- loading


def normalise(series: pd.Series, usd_per_unit: bool) -> pd.Series:
    """Return the series as USD per one foreign unit (reciprocal when quoted foreign units per USD)."""
    return series if usd_per_unit else 1.0 / series


def load_rates(codes: list[str] | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """Daily USD-per-foreign-unit rates, one column per currency code; NaN where a series has no observation."""
    columns = {}
    for code in codes or list(CURRENCIES):
        cur = CURRENCIES[code]
        columns[code] = normalise(fred.series(cur.series_id, refresh=refresh), cur.usd_per_unit).rename(code)
    return pd.DataFrame(columns).sort_index()


def coverage(rates: pd.DataFrame) -> pd.DataFrame:
    """First date, last date and number of observations per currency."""
    return pd.DataFrame(
        {
            "currency": rates.columns,
            "series": [CURRENCIES[c].series_id for c in rates.columns],
            "first": [rates[c].first_valid_index() for c in rates.columns],
            "last": [rates[c].last_valid_index() for c in rates.columns],
            "observations": [int(rates[c].count()) for c in rates.columns],
        }
    )


# ----------------------------------------------------------------------- returns, vol


def log_returns(rates: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    """Log returns between consecutive observations of each series (NaN where it has no observation)."""
    if isinstance(rates, pd.Series):
        return np.log(rates.dropna()).diff().reindex(rates.index)
    return rates.apply(log_returns)


def rolling_vol(rates: pd.DataFrame | pd.Series, window: int = 30) -> pd.DataFrame | pd.Series:
    """Rolling annualised volatility in per cent over ``window`` observations."""
    if isinstance(rates, pd.Series):
        returns = log_returns(rates).dropna()
        return (stats.rolling_volatility(returns, window, TRADING_DAYS) * 100.0).reindex(rates.index)
    return rates.apply(lambda s: rolling_vol(s, window))


# ---------------------------------------------------------------------- instability


def instability_cutoff(vol_history: pd.Series, method: str = "relative", threshold: float = 0.90) -> float:
    """Volatility level (annualised %) above which a day counts as unstable.

    ``method="relative"``: ``threshold`` is a quantile (0-1) of the series' own rolling volatility.
    ``method="absolute"``: ``threshold`` is the cut-off itself, in per cent.
    """
    if method == "relative":
        if not 0 < threshold < 1:
            raise ValueError("relative threshold must be a quantile strictly between 0 and 1")
        return float(vol_history.dropna().quantile(threshold))
    if method == "absolute":
        return float(threshold)
    raise ValueError(f"unknown method {method!r}")


def instability_flag(vol: pd.Series, cutoff: float) -> pd.Series:
    """True where rolling volatility is strictly above ``cutoff`` (missing volatility is never flagged)."""
    return (vol > cutoff).fillna(False)


def instability_periods(flag: pd.Series, vol: pd.Series, merge_days: int = 30) -> pd.DataFrame:
    """Runs of unstable days as periods.

    Columns: start, end, days (calendar), peak_vol, peak_date, mean_vol. Runs separated by ``merge_days``
    calendar days or fewer are merged, because a series hovering around its cut-off flips on and off.
    """
    cols = ["start", "end", "days", "peak_vol", "peak_date", "mean_vol"]
    flag = flag.astype(bool)
    run_id = (flag != flag.shift()).cumsum()
    runs = [(g.index[0], g.index[-1]) for _, g in flag[flag].groupby(run_id[flag])]
    merged: list[list[pd.Timestamp]] = []
    for start, end in runs:
        if merged and (start - merged[-1][1]).days <= merge_days:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    rows = []
    for start, end in merged:
        inside = vol.loc[start:end].dropna()
        rows.append(
            {
                "start": start,
                "end": end,
                "days": (end - start).days + 1,
                "peak_vol": inside.max(),
                "peak_date": inside.idxmax(),
                "mean_vol": inside.mean(),
            }
        )
    return pd.DataFrame(rows, columns=cols)


def instability_summary(
    rates: pd.DataFrame, *, window: int = 30, method: str = "relative", threshold: float = 0.90, merge_days: int = 30
) -> pd.DataFrame:
    """Per currency: cut-off, share of days flagged, number of periods and the longest one."""
    rows = []
    for code in rates.columns:
        vol = rolling_vol(rates[code], window)
        cutoff = instability_cutoff(vol, method, threshold)
        flag = instability_flag(vol, cutoff)
        periods = instability_periods(flag, vol, merge_days)
        longest = periods.loc[periods["days"].idxmax()] if len(periods) else None
        rows.append(
            {
                "currency": code,
                "cutoff_vol": cutoff,
                "share_days_unstable": float(flag[vol.notna()].mean()),
                "periods": len(periods),
                "longest_start": longest["start"] if longest is not None else pd.NaT,
                "longest_end": longest["end"] if longest is not None else pd.NaT,
                "longest_days": int(longest["days"]) if longest is not None else 0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- depreciation


def horizon_change(rate: pd.Series, days: int) -> pd.DataFrame:
    """Change over ``days`` calendar days ending at each observation, in per cent.

    The start of each window is the last observation on or before ``end - days``; windows whose start
    is more than ``MAX_STALE_DAYS`` earlier than that (a data gap) or does not exist are dropped.
    Columns (indexed by window end): start, start_rate, end_rate, change_pct.
    """
    s = rate.dropna()
    idx = s.index
    pos = idx.searchsorted(idx - pd.Timedelta(days=days), side="right") - 1
    ok = pos >= 0
    start = idx[np.where(ok, pos, 0)]
    ok &= (idx - start).days <= days + MAX_STALE_DAYS
    out = pd.DataFrame(
        {
            "start": start[ok],
            "start_rate": s.to_numpy()[pos[ok]],
            "end_rate": s.to_numpy()[ok],
        },
        index=idx[ok],
    )
    out["change_pct"] = (out["end_rate"] / out["start_rate"] - 1.0) * 100.0
    return out


def worst_episodes(rate: pd.Series, days: int, n: int = 3) -> pd.DataFrame:
    """The ``n`` largest non-overlapping falls of the foreign currency over ``days`` calendar days.

    Columns: start, end, start_rate, end_rate, change_pct (negative = depreciation).
    """
    windows = horizon_change(rate, days)
    available = windows.copy()
    rows = []
    while len(rows) < n and not available.empty:
        end = available["change_pct"].idxmin()
        row = available.loc[end]
        if row["change_pct"] >= 0:
            break
        rows.append(
            {"start": row["start"], "end": end, "start_rate": row["start_rate"], "end_rate": row["end_rate"], "change_pct": row["change_pct"]}
        )
        # Drop every window that overlaps [start, end]: those ending between start and end + days.
        available = available[(available.index < row["start"]) | (available.index > end + pd.Timedelta(days=days))]
    return pd.DataFrame(rows, columns=["start", "end", "start_rate", "end_rate", "change_pct"])


def episode_table(rates: pd.DataFrame, horizons: tuple[int, ...] = (30, 90), n: int = 3) -> pd.DataFrame:
    """Top ``n`` depreciation episodes per currency and horizon."""
    frames = []
    for code in rates.columns:
        for days in horizons:
            ep = worst_episodes(rates[code], days, n)
            ep.insert(0, "horizon_days", days)
            ep.insert(0, "currency", code)
            frames.append(ep)
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------ cross-currency


def volatility_ranking(rates: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Annualised volatility of daily log returns per currency over ``[start, end]``, highest first.

    Also reports the worst 30- and 90-day depreciation inside the window.
    """
    window = rates.loc[start:end]
    rows = []
    for code in window.columns:
        s = window[code].dropna()
        if len(s) < 3:
            continue
        returns = log_returns(s).dropna()
        w30, w90 = worst_episodes(s, 30, 1), worst_episodes(s, 90, 1)
        rows.append(
            {
                "currency": code,
                "vol_pct": stats.annualised_volatility(returns, TRADING_DAYS) * 100.0,
                "observations": len(s),
                "first": s.index[0],
                "worst_30d_pct": w30["change_pct"].iloc[0] if len(w30) else np.nan,
                "worst_90d_pct": w90["change_pct"].iloc[0] if len(w90) else np.nan,
            }
        )
    out = pd.DataFrame(rows).sort_values("vol_pct", ascending=False).reset_index(drop=True)
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def largest_moves(rates: pd.DataFrame, n: int = 1) -> pd.DataFrame:
    """The ``n`` largest absolute one-day moves per currency (log return, per cent, signed)."""
    rows = []
    for code in rates.columns:
        r = log_returns(rates[code]).dropna()
        for date in r.abs().nlargest(n).index:
            rows.append({"currency": code, "date": date, "move_pct": r[date] * 100.0})
    return pd.DataFrame(rows)


def return_correlation(rates: pd.DataFrame, freq: str = "D", start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Correlation matrix of log returns.

    ``freq="D"``: daily returns after carrying the last rate forward at most 5 days over local holidays.
    ``freq="W"``: weekly returns from Friday-or-earlier rates, which reduces the effect of time zones
    and holidays. Returns are measured in USD per foreign unit, so a shared dollar factor is built in.
    """
    window = rates.loc[start:end].ffill(limit=5)
    if freq == "W":
        window = window.resample("W-FRI").last()
    elif freq != "D":
        raise ValueError("freq must be 'D' or 'W'")
    return np.log(window).diff().corr()


def rebased(rates: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Rates rescaled to 100 on the first date at which every column has an observation."""
    window = rates.loc[start:end].dropna()
    return window.apply(stats.rebase)


# ---------------------------------------------------------------------------- main


def format_table(frame: pd.DataFrame, digits: int = 2) -> pd.DataFrame:
    """Display copy of a table: dates as YYYY-MM-DD, floats rounded."""
    out = frame.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(digits)
    return out


def main() -> None:
    rates = load_rates()
    print("== Coverage (USD per foreign unit, daily) ==")
    print(format_table(coverage(rates)).to_string(index=False))

    common_start = max(rates[c].first_valid_index() for c in rates)
    print(f"\n== Volatility ranking, common sample {common_start:%Y-%m-%d} to {rates.index[-1]:%Y-%m-%d} ==")
    print(format_table(volatility_ranking(rates, common_start.strftime("%Y-%m-%d"))).to_string(index=False))

    print("\n== Worst 30-day and 90-day depreciation, full history of each series ==")
    worst = episode_table(rates, n=1)
    print(format_table(worst.drop(columns=["start_rate", "end_rate"])).to_string(index=False))

    print("\n== Top 3 non-overlapping 90-day depreciation episodes ==")
    top90 = episode_table(rates, horizons=(90,), n=3).drop(columns=["start_rate", "end_rate"])
    print(format_table(top90).to_string(index=False))

    gfc = top90[(top90["end"] >= "2008-09-15") & (top90["end"] <= "2008-12-31")]
    print(f"\nCurrencies with a top-3 90-day depreciation window ending 2008-09-15 to 2008-12-31: {gfc['currency'].nunique()} of {len(rates.columns)} ({', '.join(sorted(gfc['currency'].unique()))})")

    print("\n== Largest one-day move per currency, full history (USD per unit, so negative = depreciation) ==")
    print(format_table(largest_moves(rates)).to_string(index=False))

    print("\n== Instability, 30-day window ==")
    for method, threshold in [("relative", 0.90), ("absolute", 15.0)]:
        label = "own 90th percentile" if method == "relative" else "annualised vol above 15%"
        summary = instability_summary(rates, window=30, method=method, threshold=threshold)
        print(f"-- cut-off: {label} (periods merged if less than 30 days apart)")
        print(format_table(summary, 3).to_string(index=False))

    corr = return_correlation(rates, "W", start=common_start.strftime("%Y-%m-%d"))
    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack().dropna().sort_values()
    print(f"\n== Weekly return correlations since {common_start:%Y-%m-%d} ==")
    print("Highest:", ", ".join(f"{a}-{b} {v:.2f}" for (a, b), v in pairs.tail(4).iloc[::-1].items()))
    print("Lowest: ", ", ".join(f"{a}-{b} {v:.2f}" for (a, b), v in pairs.head(4).items()))


if __name__ == "__main__":
    main()
