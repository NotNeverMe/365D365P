"""Unit tests (small series with hand-computed answers) plus sanity checks on the cached FRED data."""

import numpy as np
import pandas as pd
import pytest

import fx_volatility as fx
from core import fred


def daily(values, start="2023-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


# ------------------------------------------------------------------ normalisation and returns


def test_normalise_inverts_foreign_per_usd_quotes():
    quoted_foreign_per_usd = pd.Series([2.0, 4.0])
    assert list(fx.normalise(quoted_foreign_per_usd, usd_per_unit=False)) == [0.5, 0.25]
    assert list(fx.normalise(quoted_foreign_per_usd, usd_per_unit=True)) == [2.0, 4.0]


def test_a_fall_in_the_normalised_series_is_a_depreciation_for_both_quote_conventions():
    # Yen: 100 -> 125 per USD means the yen lost value. Pound: 1.25 -> 1.00 USD per GBP means the same for sterling.
    yen = fx.normalise(pd.Series([100.0, 125.0]), usd_per_unit=False)
    pound = fx.normalise(pd.Series([1.25, 1.00]), usd_per_unit=True)
    assert yen.iloc[1] < yen.iloc[0] and pound.iloc[1] < pound.iloc[0]
    assert yen.iloc[1] / yen.iloc[0] - 1 == pytest.approx(-0.20)


def test_log_returns_by_hand():
    r = fx.log_returns(daily([100.0, 110.0, 99.0]))
    assert np.isnan(r.iloc[0])
    assert r.iloc[1] == pytest.approx(np.log(1.1))
    assert r.iloc[2] == pytest.approx(np.log(0.9))


def test_log_returns_span_a_missing_day_instead_of_dropping_it():
    s = daily([100.0, np.nan, 121.0])
    r = fx.log_returns(s)
    assert np.isnan(r.iloc[1])
    assert r.iloc[2] == pytest.approx(np.log(1.21))


def test_rolling_vol_of_alternating_returns():
    # Returns +1%, -1%, +1%, ...: any 2-return window has sample sd |0.02| / sqrt(2).
    returns = np.array([0.01, -0.01] * 5)
    rates = daily(100 * np.exp(np.r_[0.0, np.cumsum(returns)]))
    vol = fx.rolling_vol(rates, window=2).dropna()
    expected = 0.02 / np.sqrt(2) * np.sqrt(252) * 100
    assert vol.iloc[-1] == pytest.approx(expected)
    assert expected == pytest.approx(22.45, abs=0.01)


def test_rolling_vol_is_zero_for_constant_growth_and_nan_before_window():
    rates = daily(100 * 1.01 ** np.arange(10))
    vol = fx.rolling_vol(rates, window=4)
    assert vol.iloc[:4].isna().all()  # needs 4 returns, the first of which is at index 1
    assert vol.dropna().abs().max() < 1e-9


# ------------------------------------------------------------------ instability


def test_relative_cutoff_is_a_quantile_and_absolute_is_taken_as_given():
    vol = pd.Series(np.arange(1.0, 11.0))
    assert fx.instability_cutoff(vol, "relative", 0.90) == pytest.approx(9.1)  # 9 + 0.1 * (10 - 9)
    assert fx.instability_cutoff(vol, "absolute", 15.0) == 15.0
    with pytest.raises(ValueError):
        fx.instability_cutoff(vol, "relative", 1.5)
    with pytest.raises(ValueError):
        fx.instability_cutoff(vol, "median")


def test_flag_is_strictly_above_cutoff_and_ignores_missing_vol():
    flag = fx.instability_flag(pd.Series([1.0, 2.0, 3.0, np.nan, 10.0]), cutoff=3.0)
    assert list(flag) == [False, False, False, False, True]


def test_flagged_share_under_the_relative_rule_is_the_complement_of_the_quantile():
    vol = pd.Series(np.arange(1.0, 101.0))
    flag = fx.instability_flag(vol, fx.instability_cutoff(vol, "relative", 0.90))
    assert flag.sum() == 10


def make_flag():
    # Unstable on days 1-3 and 14-15 of January; the gap between runs is 11 days.
    flag = daily([True] * 3 + [False] * 10 + [True] * 2 + [False] * 3)
    vol = daily([5, 6, 7] + [1] * 10 + [8, 9] + [1] * 3)
    return flag.astype(bool), vol


def test_instability_periods_merge_runs_that_are_close():
    flag, vol = make_flag()
    merged = fx.instability_periods(flag, vol, merge_days=30)
    assert len(merged) == 1
    row = merged.iloc[0]
    assert (row["start"], row["end"], row["days"]) == (pd.Timestamp("2023-01-01"), pd.Timestamp("2023-01-15"), 15)
    assert row["peak_vol"] == 9 and row["peak_date"] == pd.Timestamp("2023-01-15")


def test_instability_periods_stay_separate_when_gap_is_longer_than_merge_days():
    flag, vol = make_flag()
    split = fx.instability_periods(flag, vol, merge_days=5)
    assert list(split["days"]) == [3, 2]
    assert list(split["peak_vol"]) == [7, 9]
    assert split.loc[0, "mean_vol"] == pytest.approx(6.0)


def test_instability_periods_empty_without_flags():
    flag, vol = daily([False] * 5), daily([1] * 5)
    assert fx.instability_periods(flag, vol).empty


# ------------------------------------------------------------------ depreciation windows


def test_horizon_change_by_hand():
    s = daily([100.0, 101.0, 102.0, 90.0, 91.0, 92.0])
    out = fx.horizon_change(s, 3)
    assert list(out.index) == list(s.index[3:])  # the first three days have no window start 3 days earlier
    assert out["change_pct"].iloc[0] == pytest.approx(-10.0)
    assert out["change_pct"].iloc[1] == pytest.approx((91 / 101 - 1) * 100)
    assert out["start"].iloc[0] == pd.Timestamp("2023-01-01")


def test_horizon_change_uses_last_observation_before_a_weekend():
    # Fri 6 Jan and Mon 9 Jan only. A 3-day window ending Monday starts on Friday itself.
    s = pd.Series([100.0, 95.0], index=pd.to_datetime(["2023-01-06", "2023-01-09"]))
    out = fx.horizon_change(s, 3)
    assert len(out) == 1 and out["start"].iloc[0] == pd.Timestamp("2023-01-06")
    assert out["change_pct"].iloc[0] == pytest.approx(-5.0)


def test_horizon_change_drops_windows_that_straddle_a_data_gap():
    s = pd.Series([100.0, 50.0], index=pd.to_datetime(["2023-01-01", "2023-02-15"]))
    assert fx.horizon_change(s, 3).empty  # the only earlier observation is 45 days old


def test_worst_episodes_are_non_overlapping_and_stop_when_no_fall_remains():
    values = [100.0] * 10 + [80.0] * 20 + [100.0] * 20 + [90.0] * 10  # crash on 11 Jan, partial one on 20 Feb
    s = daily(values)
    eps = fx.worst_episodes(s, 5, n=5)
    assert len(eps) == 2
    assert list(eps["change_pct"].round(6)) == [-20.0, -10.0]
    assert eps.loc[0, "end"] == pd.Timestamp("2023-01-11") and eps.loc[0, "start"] == pd.Timestamp("2023-01-06")
    assert eps.loc[1, "end"] == pd.Timestamp("2023-02-20")
    assert eps.loc[0, "end"] < eps.loc[1, "start"]


def test_episode_table_has_one_block_per_currency_and_horizon():
    rates = pd.DataFrame({"AAA": daily([100.0] * 5 + [80.0] * 100), "BBB": daily([100.0] * 105)})
    table = fx.episode_table(rates, horizons=(30, 90), n=1)
    assert set(zip(table["currency"], table["horizon_days"])) == {("AAA", 30), ("AAA", 90)}
    assert (table["change_pct"] < 0).all()


# ------------------------------------------------------------------ cross-currency


def test_return_correlation_of_a_series_and_its_reciprocal_is_minus_one():
    rng = np.random.default_rng(0)
    a = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 80))), index=pd.bdate_range("2023-01-02", periods=80))
    rates = pd.DataFrame({"A": a, "B": 1 / a, "C": 3 * a})
    corr = fx.return_correlation(rates, "D")
    assert corr.loc["A", "B"] == pytest.approx(-1.0)
    assert corr.loc["A", "C"] == pytest.approx(1.0)
    weekly = fx.return_correlation(rates, "W")
    assert weekly.loc["A", "B"] == pytest.approx(-1.0)
    with pytest.raises(ValueError):
        fx.return_correlation(rates, "M")


def test_volatility_ranking_orders_by_annualised_volatility():
    idx = pd.bdate_range("2023-01-02", periods=61)
    wild = 100 * np.exp(np.r_[0.0, np.cumsum([0.02, -0.02] * 30)])
    calm = 100 * np.exp(np.r_[0.0, np.cumsum([0.005, -0.005] * 30)])
    rates = pd.DataFrame({"CALM": calm, "WILD": wild}, index=idx)
    ranking = fx.volatility_ranking(rates)
    assert list(ranking["currency"]) == ["WILD", "CALM"]
    assert list(ranking["rank"]) == [1, 2]
    expected = np.std([0.02, -0.02] * 30, ddof=1) * np.sqrt(252) * 100
    assert ranking.loc[0, "vol_pct"] == pytest.approx(expected)
    assert ranking.loc[0, "observations"] == 61


def test_rebased_starts_at_100_on_first_common_date():
    rates = pd.DataFrame({"A": [np.nan, 2.0, 4.0], "B": [1.0, 5.0, 10.0]}, index=pd.date_range("2023-01-02", periods=3))
    out = fx.rebased(rates)
    assert out.index[0] == pd.Timestamp("2023-01-03")
    assert list(out["A"]) == [100.0, 200.0] and list(out["B"]) == [100.0, 200.0]


def test_largest_moves_picks_the_biggest_absolute_return():
    rates = pd.DataFrame({"A": [100.0, 101.0, 80.0, 81.0]}, index=pd.date_range("2023-01-02", periods=4))
    moves = fx.largest_moves(rates)
    assert moves.loc[0, "date"] == pd.Timestamp("2023-01-04")
    assert moves.loc[0, "move_pct"] == pytest.approx(np.log(80 / 101) * 100)


# ------------------------------------------------------------------ real cached data


@pytest.fixture(scope="module")
def rates():
    return fx.load_rates()


def test_all_twelve_series_load_with_long_current_history(rates):
    assert list(rates.columns) == list(fx.CURRENCIES) and len(rates.columns) == 12
    cov = fx.coverage(rates)
    assert (cov["observations"] > 6000).all()
    assert (cov["last"] >= pd.Timestamp("2026-09-01")).all()
    assert cov.set_index("currency").loc["EUR", "first"] == pd.Timestamp("1999-01-04")
    assert (rates.min() > 0).all()


def test_normalisation_against_the_raw_fred_series(rates):
    raw_yen = fred.series("DEXJPUS")  # yen per USD
    raw_euro = fred.series("DEXUSEU")  # USD per euro
    day = pd.Timestamp("2008-10-27")
    assert rates.loc[day, "JPY"] == pytest.approx(1.0 / raw_yen.loc[day])
    assert rates.loc[day, "EUR"] == pytest.approx(raw_euro.loc[day])


def test_known_one_day_moves_by_date_and_sign(rates):
    moves = fx.largest_moves(rates).set_index("currency")
    assert moves.loc["GBP", "date"] == pd.Timestamp("2016-06-24") and -9 < moves.loc["GBP", "move_pct"] < -7
    assert moves.loc["CHF", "date"] == pd.Timestamp("2015-01-15") and moves.loc["CHF", "move_pct"] > 10  # franc jumps vs USD
    assert moves.loc["THB", "date"] == pd.Timestamp("1997-07-02") and moves.loc["THB", "move_pct"] < -15


def test_worst_euro_30_day_fall_matches_hand_calculation(rates):
    ep = fx.worst_episodes(rates["EUR"], 30, 1).iloc[0]
    raw = fred.series("DEXUSEU")
    by_hand = (raw.loc[ep["end"]] / raw.loc[ep["start"]] - 1) * 100
    assert ep["change_pct"] == pytest.approx(by_hand)
    assert 30 <= (ep["end"] - ep["start"]).days <= 33  # starts on the last rate on or before the 30th day back
    assert -16 < ep["change_pct"] < -13


def test_relative_rule_flags_about_ten_percent_of_days_for_every_currency(rates):
    summary = fx.instability_summary(rates, window=30, method="relative", threshold=0.90)
    assert summary["share_days_unstable"].between(0.099, 0.101).all()
    assert (summary["periods"] > 5).all()


def test_ranking_since_1999_puts_brl_and_zar_on_top_and_cny_last(rates):
    ranking = fx.volatility_ranking(rates, "1999-01-04")
    assert set(ranking["currency"].head(2)) == {"BRL", "ZAR"}
    assert ranking["currency"].iloc[-1] == "CNY"
    assert ranking["vol_pct"].is_monotonic_decreasing
