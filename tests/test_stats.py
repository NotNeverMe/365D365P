import numpy as np
import pandas as pd
import pytest

from core import stats


def test_cagr():
    assert stats.cagr(100, 121, 2) == pytest.approx(0.10)
    with pytest.raises(ValueError):
        stats.cagr(0, 1, 1)
    with pytest.raises(ValueError):
        stats.cagr(1, 2, 0)


def test_rebase_uses_first_valid_value():
    s = pd.Series([np.nan, 50.0, 75.0, 100.0])
    assert stats.rebase(s).dropna().tolist() == [100.0, 150.0, 200.0]


def test_yoy_change_monthly():
    s = pd.Series(np.arange(1.0, 25.0))
    out = stats.yoy_change(s, periods=12)
    assert out.iloc[12] == pytest.approx(1200.0)  # 13 vs 1 -> +1200%
    assert out.iloc[:12].isna().all()


def test_yoy_change_is_calendar_based_across_a_gap():
    idx = pd.date_range("2024-01-01", periods=26, freq="MS")
    s = pd.Series(np.arange(1.0, 27.0), index=idx).drop(pd.Timestamp("2024-10-01"))
    out = stats.yoy_change(s)
    assert np.isnan(out[pd.Timestamp("2025-10-01")])  # no Oct 2024 to compare with
    assert out[pd.Timestamp("2025-11-01")] == pytest.approx((23 / 11 - 1) * 100)
    assert out[pd.Timestamp("2025-09-01")] == pytest.approx((21 / 9 - 1) * 100)


def test_volatility_scaling():
    rng = np.random.default_rng(3)
    r = pd.Series(rng.normal(0, 0.01, 5000))
    assert stats.annualised_volatility(r) == pytest.approx(0.01 * np.sqrt(252), rel=0.05)
    assert stats.rolling_volatility(r, window=30).iloc[:29].isna().all()


def test_trend_per_year():
    years = np.arange(2000, 2010)
    assert stats.trend_per_year(years, 2 * years + 5) == pytest.approx(2.0)
    assert np.isnan(stats.trend_per_year([2000, 2001], [1, 2]))
