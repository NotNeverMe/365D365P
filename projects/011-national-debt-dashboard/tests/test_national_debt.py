"""Unit tests for national_debt: hand-computed synthetic frames, then checks against the cached data."""

import math

import numpy as np
import pandas as pd
import pytest

import national_debt as nd


def frame(rows: dict[tuple[str, int], dict[str, float]]) -> pd.DataFrame:
    """Wide (iso3, year) frame with the inputs and the World Bank cross-check column (NaN when not given)."""
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.MultiIndex.from_tuples(df.index, names=["iso3", "year"])
    for col in [*nd.INPUTS, *nd.CROSS_CHECK]:
        if col not in df:
            df[col] = np.nan
    return nd.add_ratios(df.sort_index())


@pytest.fixture
def toy() -> pd.DataFrame:
    return frame(
        {
            ("USA", 2020): {"debt": 100.0, "revenue": 25.0, "interest_share": 10.0, "expense": 40.0},
            ("USA", 2021): {"debt": 110.0, "revenue": 22.0, "interest_share": 12.0, "expense": 44.0},
            ("GBR", 2021): {"debt": 80.0, "revenue": 40.0, "interest_share": 5.0, "expense": 50.0},
            ("DEU", 2021): {"debt": 60.0},  # debt but no revenue
            ("FRA", 2021): {"revenue": 45.0},  # revenue but no debt
            ("JPN", 2018): {"debt": 200.0, "revenue": 10.0},
        }
    )


def test_add_ratios_hand_computed(toy):
    row = toy.loc[("USA", 2020)]
    assert row["debt_to_revenue"] == pytest.approx(4.0)  # 100 / 25 years of revenue
    assert row["interest_gdp"] == pytest.approx(4.0)  # 10% of a budget worth 40% of GDP
    assert row["interest_to_revenue"] == pytest.approx(16.0)  # 4 / 25 x 100
    assert math.isnan(toy.loc[("DEU", 2021), "debt_to_revenue"])  # a missing input gives NaN, never a guess


def test_add_ratios_treats_non_positive_revenue_as_missing():
    df = frame({("USA", 2020): {"debt": 50.0, "revenue": 0.0, "interest_share": 10.0, "expense": 20.0}})
    assert math.isnan(df.loc[("USA", 2020), "debt_to_revenue"])
    assert math.isnan(df.loc[("USA", 2020), "interest_to_revenue"])
    assert np.isfinite(df.loc[("USA", 2020), "interest_gdp"])  # does not need revenue


def test_coverage_by_year_counts_countries(toy):
    cov = nd.coverage_by_year(toy)
    assert cov.loc[2021, "debt"] == 3 and cov.loc[2021, "revenue"] == 3
    assert cov.loc[2021, "debt_to_revenue"] == 2  # USA and GBR
    assert cov.loc[2021, "interest_to_revenue"] == 2
    assert cov.loc[2018, "debt_to_revenue"] == 1  # JPN
    assert cov.loc[2021, "debt_share"] == pytest.approx(3 / len(nd.wb.names()))


def test_coverage_by_country_keeps_countries_without_debt(toy):
    cov = nd.coverage_by_country(toy, first_year=2019).set_index("iso3")
    assert set(cov.index) == {"USA", "GBR", "DEU", "FRA", "JPN"}  # nobody dropped
    assert cov.loc["USA", "debt_years"] == 2 and cov.loc["USA", "debt_to_revenue_years"] == 2
    assert pd.isna(cov.loc["FRA", "debt_first_year"]) and cov.loc["FRA", "debt_years"] == 0
    assert cov.loc["JPN", "debt_years"] == 0  # its only year (2018) is before first_year=2019
    assert cov.loc["JPN", "debt_first_year"] == 2018 and cov.loc["JPN", "debt_last_year"] == 2018
    assert (cov["possible_years"] == 3).all()  # 2019, 2020, 2021


def test_broad_year_uses_share_of_peak():
    rows = {}
    for year, n in {2018: 10, 2019: 8, 2020: 7, 2021: 3}.items():
        for i in range(n):
            rows[(f"C{i:02d}", year)] = {"debt": 50.0, "revenue": 25.0}
    df = frame(rows)
    assert nd.broad_year(df, "debt_to_revenue", min_share_of_peak=0.75) == 2019  # 8 >= 7.5, 7 < 7.5
    assert nd.broad_year(df, "debt_to_revenue", min_share_of_peak=0.3) == 2021
    assert nd.broad_year(df, "debt_to_revenue", min_share_of_peak=1.0) == 2018


def test_latest_complete_uses_same_year_inputs_and_lag(toy):
    out = nd.latest_complete(toy, ["debt", "revenue", "debt_to_revenue"], 2021).set_index("iso3")
    assert set(out.index) == {"USA", "GBR"}
    assert out.loc["USA", "obs_year"] == 2021 and out.loc["USA", "debt_to_revenue"] == pytest.approx(5.0)
    lagged = nd.latest_complete(toy, ["debt", "revenue", "debt_to_revenue"], 2021, max_lag=3).set_index("iso3")
    assert lagged.loc["JPN", "obs_year"] == 2018 and lagged.loc["JPN", "debt_to_revenue"] == pytest.approx(20.0)
    assert "JPN" not in set(nd.latest_complete(toy, ["debt_to_revenue"], 2021, max_lag=2)["iso3"])  # 2018 is three years back


def test_excluded_countries_explains_each_absence(toy):
    out = nd.excluded_countries(toy, "debt_to_revenue", 2021).set_index("iso3")
    assert set(out.index) == {"DEU", "FRA", "JPN"}  # USA and GBR are plotted
    assert out.loc["DEU", "has_in_window"] == "debt" and out.loc["DEU", "missing_in_window"] == "revenue"
    assert out.loc["FRA", "has_in_window"] == "revenue" and out.loc["FRA", "missing_in_window"] == "debt"
    assert out.loc["JPN", "has_in_window"] == "nothing"


def test_rank_comparison_hand_computed():
    df = frame(
        {
            ("USA", 2020): {"debt": 100.0, "revenue": 50.0},  # 2 years of revenue
            ("GBR", 2020): {"debt": 80.0, "revenue": 10.0},  # 8
            ("DEU", 2020): {"debt": 60.0, "revenue": 20.0},  # 3
        }
    )
    ranks = nd.rank_comparison(df, 2020).set_index("iso3")
    assert list(ranks["rank_debt_gdp"]) == [1, 2, 3]  # USA, GBR, DEU in debt-to-GDP order
    assert ranks.loc["GBR", "rank_debt_revenue"] == 1 and ranks.loc["DEU", "rank_debt_revenue"] == 2 and ranks.loc["USA", "rank_debt_revenue"] == 3
    assert ranks.loc["USA", "rank_shift"] == -2 and ranks.loc["GBR", "rank_shift"] == 1 and ranks.loc["DEU", "rank_shift"] == 1
    # Spearman by hand: ranks (1,2,3) vs (3,1,2); sum d^2 = 6 -> 1 - 6*6/(3*8) = -0.5
    assert nd.rank_correlation(ranks.reset_index()) == pytest.approx(-0.5)


def test_interest_burden_sorted_and_needs_all_inputs(toy):
    out = nd.interest_burden(toy, 2021)
    assert list(out["iso3"]) == ["USA", "GBR"]  # USA: 0.12*44/22 = 24%, GBR: 0.05*50/40 = 6.25%
    assert out["interest_to_revenue"].iloc[0] == pytest.approx(24.0)
    assert out["interest_to_revenue"].iloc[1] == pytest.approx(6.25)


def test_trajectories_filters_countries_and_years(toy):
    out = nd.trajectories(toy, ["USA", "JPN"], "debt", 2019, 2021)
    assert list(zip(out["iso3"], out["year"], out["value"])) == [("USA", 2020, 100.0), ("USA", 2021, 110.0)]


def test_formula_check_compares_with_world_bank_series():
    df = frame(
        {
            ("USA", 2020): {"interest_share": 10.0, "expense": 40.0, "revenue": 20.0, "wb_interest_to_revenue": 20.0},  # exact
            ("GBR", 2020): {"interest_share": 10.0, "expense": 40.0, "revenue": 20.0, "wb_interest_to_revenue": 17.0},  # 3 points off
            ("DEU", 2020): {"interest_share": 10.0, "expense": 40.0, "revenue": 20.0},  # no World Bank value: ignored
        }
    )
    check = nd.formula_check(df, tolerance=1.0)
    assert check["n"] == 2 and check["share_within_tolerance"] == pytest.approx(0.5)
    assert check["median_abs_gap"] == pytest.approx(1.5)
    assert check["n_off"] == 1 and check["share_derived_higher_when_off"] == 1.0  # GBR: derived 20 vs World Bank 17


def test_us_extremes_label_quarters():
    idx = pd.to_datetime(["2020-01-01", "2020-04-01", "2020-10-01"])
    ex = nd.us_extremes(pd.Series([50.0, 90.0, 70.0], index=idx))
    assert ex == {"min": ("2020-Q1", 50.0), "max": ("2020-Q2", 90.0), "latest": ("2020-Q4", 70.0)}


def test_us_world_bank_comparison_averages_quarters():
    hist = pd.DataFrame({"gross": [10.0, 20.0, 30.0, 40.0], "held_by_public": [1.0, 2.0, 3.0, 4.0]}, index=pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"]))
    df = frame({("USA", 2020): {"debt": 25.0}, ("GBR", 2020): {"debt": 99.0}})
    out = nd.us_world_bank_comparison(df, hist)
    assert out.loc[2020, "world_bank"] == 25.0 and out.loc[2020, "gross"] == pytest.approx(25.0) and out.loc[2020, "held_by_public"] == pytest.approx(2.5)


# ----------------------------------------------------------------------------- real cached data


@pytest.fixture(scope="module")
def real() -> pd.DataFrame:
    return nd.load()


def test_real_coverage_is_patchy_as_documented(real):
    assert real["debt"].dropna().index.get_level_values("iso3").nunique() >= 100  # 109 when written
    by_year = nd.coverage_by_year(real)
    assert by_year.loc[2022, "debt_to_revenue"] == 43
    assert by_year.loc[2022, "interest_to_revenue"] > 100
    by_country = nd.coverage_by_country(real).set_index("iso3")
    for iso3 in ["JPN", "FRA", "CHN", "GRC", "ARG"]:  # large economies with no debt figure at all
        if iso3 in by_country.index:
            assert by_country.loc[iso3, "debt_years"] == 0
    assert nd.broad_year(real) == 2022


def test_real_ratios_match_a_hand_calculation_from_raw_series(real):
    from core import worldbank as wb

    def raw(code, iso3, year):
        frame = wb.indicator(code)
        return float(frame[(frame["iso3"] == iso3) & (frame["year"] == year)]["value"].iloc[0])

    # Somalia 2022: debt 43.4% of GDP over revenue 2.6% of GDP is about 16.8 years of revenue.
    expected = raw("GC.DOD.TOTL.GD.ZS", "SOM", 2022) / raw("GC.REV.XGRT.GD.ZS", "SOM", 2022)
    assert real.loc[("SOM", 2022), "debt_to_revenue"] == pytest.approx(expected)
    assert expected == pytest.approx(16.8, abs=0.1)
    # Sri Lanka 2022: 0.413 of expense is interest, expense 15.7% of GDP, revenue 8.2% of GDP -> 79.1% of revenue.
    hand = raw("GC.XPN.INTP.ZS", "LKA", 2022) / 100 * raw("GC.XPN.TOTL.GD.ZS", "LKA", 2022) / raw("GC.REV.XGRT.GD.ZS", "LKA", 2022) * 100
    assert real.loc[("LKA", 2022), "interest_to_revenue"] == pytest.approx(hand)
    assert hand == pytest.approx(79.1, abs=0.1)


def test_real_rankings_differ_between_the_two_yardsticks(real):
    ranks = nd.rank_comparison(real, 2022).set_index("iso3")
    assert len(ranks) == 43
    assert 0.6 < nd.rank_correlation(ranks.reset_index()) < 0.9  # 0.76 when written: related but not the same ordering
    assert ranks.loc["SOM", "rank_debt_revenue"] == 1 and ranks.loc["SOM", "rank_debt_gdp"] == 32
    assert ranks.loc["HUN", "rank_shift"] < -10  # high debt-to-GDP, but a tax-heavy state
    assert ranks["rank_shift"].abs().max() >= 30


def test_real_interest_burden_2022_led_by_sri_lanka(real):
    out = nd.interest_burden(real, 2022, top=3)
    assert list(out["iso3"])[0] == "LKA" and out["interest_to_revenue"].iloc[0] > 75
    assert out["interest_to_revenue"].is_monotonic_decreasing


def test_real_formula_agrees_with_world_bank_interest_to_revenue(real):
    check = nd.formula_check(real)
    assert check["n"] > 4000
    assert check["share_within_tolerance"] > 0.85  # 88.7% when written
    assert check["correlation"] > 0.99
    assert check["share_derived_higher_when_off"] > 0.95  # 99.8% when written


def test_real_us_history_from_fred():
    hist = nd.us_history()
    gross = nd.us_extremes(hist["gross"])
    assert hist["gross"].index.min() == pd.Timestamp("1966-01-01")
    assert gross["min"][0] == "1981-Q3" and gross["min"][1] == pytest.approx(30.6, abs=0.1)
    assert gross["max"][0] == "2020-Q2" and gross["max"][1] == pytest.approx(132.7, abs=0.1)
    both = hist.dropna()  # held-by-public starts in 1970
    assert (both["gross"] >= both["held_by_public"]).all()  # gross debt includes the publicly held part
