"""Small, well-tested numeric helpers reused across projects."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cagr(start: float, end: float, years: float) -> float:
    """Compound annual growth rate between two positive levels, as a fraction."""
    if years <= 0:
        raise ValueError("years must be positive")
    if start <= 0 or end <= 0:
        raise ValueError("start and end must be positive")
    return (end / start) ** (1.0 / years) - 1.0


def rebase(series: pd.Series, base: float = 100.0) -> pd.Series:
    """Rescale so the first valid observation equals ``base``."""
    first = series.dropna().iloc[0]
    return series / first * base


def yoy_change(series: pd.Series, periods: int = 12) -> pd.Series:
    """Percentage change versus the same date one year earlier.

    With a DatetimeIndex the comparison is calendar based, so a missing month
    (for example the October 2025 US CPI, which was never published) yields NaN
    for that month and for the same month a year later, instead of silently
    shifting every later value by one position. With any other index it falls
    back to a positional change over ``periods`` observations.
    """
    if isinstance(series.index, pd.DatetimeIndex):
        prior = series.copy()
        prior.index = prior.index + pd.DateOffset(years=1)
        prior = prior[~prior.index.duplicated()]
        return (series / prior.reindex(series.index) - 1.0) * 100.0
    return series.pct_change(periods=periods) * 100.0


def annualised_volatility(log_returns: pd.Series, periods_per_year: int = 252) -> float:
    """Standard deviation of log returns scaled to a year, as a fraction."""
    return float(log_returns.std(ddof=1) * np.sqrt(periods_per_year))


def rolling_volatility(log_returns: pd.Series, window: int = 30, periods_per_year: int = 252) -> pd.Series:
    """Rolling annualised volatility of log returns, as a fraction."""
    return log_returns.rolling(window, min_periods=window).std(ddof=1) * np.sqrt(periods_per_year)


def trend_per_year(years: pd.Index | np.ndarray, values: pd.Series | np.ndarray) -> float:
    """OLS slope of ``values`` on ``years`` (units of value per year)."""
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return float("nan")
    return float(np.polyfit(x[mask], y[mask], 1)[0])
