"""Unit tests for inflation_tracker: synthetic frames with known answers, then sanity checks on the cached data."""

import numpy as np
import pandas as pd
import pytest

import inflation_tracker as it


def monthly(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


# ------------------------------------------------------------------------------------------ yoy


def test_yoy_compares_the_same_calendar_month_even_with_a_gap():
    level = monthly(100 * 1.01 ** np.arange(30))
    level.iloc[13] = np.nan  # a month that was never published
    out = it.yoy(level.to_frame("x"))["x"]
    expected = (1.01**12 - 1) * 100  # 12.6825 %
    assert out.iloc[12] == pytest.approx(expected)
    assert np.isnan(out.iloc[13]) and np.isnan(out.iloc[25])  # the gap month and the month a year later
    assert out.iloc[:12].isna().all()  # no month a year earlier
    assert np.allclose(out.drop(out.index[list(range(12)) + [13, 25]]), expected)


# ---------------------------------------------------------------------------------------- weights


def test_nnls_weights_recover_exact_weights():
    rng = np.random.default_rng(0)
    x = rng.normal(0.003, 0.004, size=(60, 4))
    true = np.array([0.5, 0.3, 0.2, 0.0])
    assert it.nnls_weights(x @ true, x) == pytest.approx(true, abs=1e-8)


def test_nnls_weights_are_never_negative():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, size=(80, 3))
    y = x @ np.array([1.0, -0.5, 0.5])  # the truth contains a negative weight
    coef = it.nnls_weights(y, x)
    assert (coef >= 0).all() and coef[1] == 0


def synthetic_levels(n=80):
    """All-items log change is exactly 0.5 a + 0.3 b + 0.2 c each month."""
    rng = np.random.default_rng(2)
    changes = pd.DataFrame(rng.normal(0.003, 0.004, size=(n, 3)), columns=["A", "B", "C"])
    head = changes @ np.array([0.5, 0.3, 0.2])
    logs = pd.concat([head.rename(it.HEADLINE), changes], axis=1).cumsum()
    index = pd.date_range("2000-01-01", periods=n, freq="MS")
    return pd.DataFrame(np.exp(logs.to_numpy()) * 100, index=index, columns=[it.HEADLINE, "A", "B", "C"])


def test_estimate_weights_recover_known_weights_and_wait_for_enough_data():
    levels = synthetic_levels()
    w = it.estimate_weights(levels, window=36, min_obs=24)
    assert w.iloc[:24].isna().all().all()  # 23 monthly changes exist by month 24, 24 by month 25
    assert w.iloc[24:].notna().all().all()
    assert w.iloc[30:].to_numpy() == pytest.approx(np.tile([0.5, 0.3, 0.2], (len(w) - 30, 1)), abs=1e-6)


def test_estimate_weights_skip_months_with_missing_levels():
    levels = synthetic_levels()
    levels.iloc[40] = np.nan
    w = it.estimate_weights(levels, window=36, min_obs=24)
    assert w.iloc[-1].to_numpy() == pytest.approx([0.5, 0.3, 0.2], abs=1e-6)  # the gap does not break the fit


# ---------------------------------------------------------------------------------- contributions


def two_category_levels():
    t = np.arange(13)
    a = 100 * 1.10 ** (t / 12)  # +10 % over the year
    b = 100 * 1.05 ** (t / 12)  # +5 % over the year
    return pd.DataFrame({it.HEADLINE: 0.6 * a + 0.4 * b, "A": a, "B": b}, index=pd.date_range("2021-01-01", periods=13, freq="MS"))


def test_contributions_are_weight_times_yoy_and_residual_closes_the_gap():
    levels = two_category_levels()
    weights = pd.DataFrame({"A": 0.6, "B": 0.4}, index=levels.index)
    parts = it.contributions(levels, weights)
    assert list(parts.index) == [levels.index[12]]  # only one month has a 12-month change
    row = parts.iloc[0]
    assert row["A"] == pytest.approx(0.6 * 10.0)  # 6.0 pp
    assert row["B"] == pytest.approx(0.4 * 5.0)  # 2.0 pp
    assert row[it.RESIDUAL] == pytest.approx(0.0, abs=1e-9)  # headline = 0.6 * 110 + 0.4 * 105 - 100 = 8.0


def test_residual_picks_up_what_wrong_weights_miss():
    levels = two_category_levels()
    weights = pd.DataFrame({"A": 0.5, "B": 0.4}, index=levels.index)  # weights sum to 0.9, not 1
    row = it.contributions(levels, weights).iloc[0]
    assert row[it.RESIDUAL] == pytest.approx(8.0 - (0.5 * 10 + 0.4 * 5))  # 1.0 pp left over


def test_contributions_use_weights_from_twelve_months_earlier():
    levels = two_category_levels()
    weights = pd.DataFrame({"A": 0.0, "B": 0.0}, index=levels.index)
    weights.loc[levels.index[0]] = [0.6, 0.4]  # only the base month has weights
    assert it.contributions(levels, weights)["A"].iloc[0] == pytest.approx(6.0)
    weights.loc[levels.index[0]] = [0.0, 0.0]
    weights.loc[levels.index[12]] = [0.6, 0.4]  # weights known only at the comparison month: not used
    assert it.contributions(levels, weights)["A"].iloc[0] == pytest.approx(0.0)


def test_month_table_is_sorted_and_includes_residual_and_shares():
    levels = two_category_levels()
    weights = pd.DataFrame({"A": 0.6, "B": 0.4}, index=levels.index)
    table = it.month_table(levels, weights, levels.index[12])
    assert list(table["category"]) == ["A", "B", it.RESIDUAL]
    assert table.loc[0, "weight_pct"] == pytest.approx(60.0) and table.loc[0, "yoy_pct"] == pytest.approx(10.0)
    assert table["share_of_headline_pct"].sum() == pytest.approx(100.0)  # 75 + 25 + 0


def test_fit_summary_reports_residual_and_weight_sums():
    parts = pd.DataFrame({it.RESIDUAL: [0.1, -0.3]}, index=pd.date_range("2022-01-01", periods=2, freq="MS"))
    weights = pd.DataFrame({"A": [0.5, 0.6, np.nan], "B": [0.45, 0.5, np.nan]})
    fit = it.fit_summary(parts, weights)
    assert fit["mean_abs_residual_pp"] == pytest.approx(0.2) and fit["max_abs_residual_pp"] == pytest.approx(0.3)
    assert (fit["weight_sum_min"], fit["weight_sum_max"]) == pytest.approx((0.95, 1.1))
    assert fit["share_months_with_a_zero_weight"] == 0.0
    weights.loc[1, "B"] = 0.0  # one of the two estimated months now has a weight at the zero bound
    assert it.fit_summary(parts, weights)["share_months_with_a_zero_weight"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------------- cross-country


@pytest.fixture
def wide():
    return pd.DataFrame(
        {"AAA": [2.0, 4.0, 12.0, np.nan], "BBB": [1.0, 1.5, 2.0, 2.5], "CCC": [np.nan, np.nan, 30.0, 40.0]},
        index=pd.Index([2020, 2021, 2022, 2023], name="year"),
    )


def test_country_summary(wide):
    s = it.country_summary(wide, ["AAA", "CCC"], 2020, 2023, {"AAA": "Alpha"}).set_index("iso3")
    assert s.loc["AAA", "country"] == "Alpha" and s.loc["CCC", "country"] == "CCC"
    assert s.loc["AAA", "mean_pct"] == pytest.approx(6.0) and s.loc["AAA", "median_pct"] == 4.0
    assert (s.loc["AAA", "peak_pct"], s.loc["AAA", "peak_year"]) == (12.0, 2022)
    assert (s.loc["AAA", "latest_pct"], s.loc["AAA", "latest_year"]) == (12.0, 2022)  # 2023 is missing
    assert (s.loc["CCC", "years_with_data"], s.loc["CCC", "years_expected"]) == (2, 4)


def test_count_above_ignores_missing_values_and_world_coverage(wide):
    assert it.count_above(wide, 2022, 10) == (2, 3)
    assert it.count_above(wide, 2023, 10) == (1, 2)
    assert it.world_coverage(wide) == {"economies": 3, "first_year": 2020, "last_year": 2023, "economies_in_last_year": 2}


def test_annual_average_inflation_needs_twelve_months():
    level = pd.concat([monthly([100.0] * 12, "2020-01-01"), monthly([110.0] * 12, "2021-01-01"), monthly([121.0] * 11, "2022-01-01")])
    out = it.annual_average_inflation(level)
    assert out[2021] == pytest.approx(10.0)
    assert np.isnan(out[2022])  # 2022 is incomplete, so no annual average


# ------------------------------------------------------------------ cached data (offline sanity)


@pytest.fixture(scope="module")
def catalog():
    return it.series_catalog()


@pytest.fixture(scope="module")
def major():
    levels = it.load_levels("Eight major groups")
    weights = it.estimate_weights(levels)
    return levels, weights, it.contributions(levels, weights)


def test_every_series_id_loads_and_runs_to_recent_data(catalog):
    assert len(catalog) == 16 and catalog["series_id"].is_unique
    assert (catalog["last"] >= "2025-09").all()
    assert (catalog["first"] <= "1993-01").all()
    used = {sid for cols in it.BREAKDOWNS.values() for sid in cols.values()} | {it.HEADLINE_ID}
    assert used == set(catalog["series_id"])


def test_october_2025_is_missing_and_not_filled(major):
    levels, _, parts = major
    assert levels.loc["2025-10-01"].isna().all()
    assert pd.Timestamp("2025-10-01") not in parts.index and pd.Timestamp("2026-10-01") not in parts.index
    assert pd.Timestamp("2025-11-01") in levels.index


def test_headline_yoy_matches_hand_calculation(major):
    levels, _, _ = major
    assert levels.loc["2026-08-01", it.HEADLINE] == pytest.approx(334.980)
    assert levels.loc["2025-08-01", it.HEADLINE] == pytest.approx(323.976)
    assert it.yoy(levels).loc["2026-08-01", it.HEADLINE] == pytest.approx((334.980 / 323.976 - 1) * 100)  # 3.3965 %


@pytest.mark.parametrize("breakdown", list(it.BREAKDOWNS))
def test_estimated_weights_are_a_plausible_partition(breakdown):
    levels = it.load_levels(breakdown)
    weights = it.estimate_weights(levels)
    fit = it.fit_summary(it.contributions(levels, weights), weights)
    assert (weights.dropna() >= 0).all().all()
    assert 0.9 < fit["weight_sum_min"] and fit["weight_sum_max"] < 1.1
    assert fit["mean_abs_residual_pp"] < 0.15
    assert fit["months"] > 300


def test_eight_group_contributions_in_the_2022_peak(major):
    levels, weights, parts = major
    head = it.yoy(levels)[it.HEADLINE].loc[parts.index]
    assert head.idxmax() == pd.Timestamp("2022-06-01")
    row = parts.loc["2022-06-01"]
    assert row.drop(it.RESIDUAL).idxmax() == "Transportation"
    assert row["Transportation"] == pytest.approx(3.15, abs=0.05)
    assert row.sum() == pytest.approx(head.max())  # categories + residual add to the headline


def test_shelter_is_the_largest_estimated_weight_in_the_split_breakdown():
    levels = it.load_levels("Housing split out (shelter separate)")
    latest = it.estimate_weights(levels).dropna().iloc[-1]
    assert latest.idxmax() == "Shelter" and 0.25 < latest["Shelter"] < 0.40


def test_world_bank_us_inflation_matches_fred_annual_average(major):
    levels, _, _ = major
    fred_annual = it.annual_average_inflation(levels[it.HEADLINE]).dropna()
    us = it.load_world_inflation()["USA"].dropna()
    common = fred_annual.index.intersection(us.index)
    assert len(common) >= 30
    assert (fred_annual[common] - us[common]).abs().max() < 0.01


def test_world_inflation_coverage_floor_and_2022_spike():
    wide = it.load_world_inflation()
    cov = it.world_coverage(wide)
    assert cov["economies"] >= 180 and cov["last_year"] >= 2024
    above, reporting = it.count_above(wide, 2022, 10)
    assert reporting > 150 and above / reporting > 0.25
