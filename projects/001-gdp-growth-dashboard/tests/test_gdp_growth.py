"""Unit tests for gdp_growth: small hand-computed frames, then sanity checks on the cached World Bank data."""

import numpy as np
import pandas as pd
import pytest

import gdp_growth as gg


def make_frame(rows):
    """rows: {iso3: {year: (level, growth_pct)}} -> frame indexed by (iso3, year)."""
    records = [(iso, year, lvl, g) for iso, years in rows.items() for year, (lvl, g) in years.items()]
    df = pd.DataFrame(records, columns=["iso3", "year", "level", "growth"]).set_index(["iso3", "year"]).sort_index()
    return df[["growth", "level"]]


@pytest.fixture
def toy():
    return make_frame(
        {
            # levels 100 -> 110 -> 99 -> 118.8, so growth is +10%, -10%, +20%
            "AAA": {2000: (100.0, np.nan), 2001: (110.0, 10.0), 2002: (99.0, -10.0), 2003: (118.8, 20.0)},
            # steady 5% a year but the 2003 level is missing
            "BBB": {2000: (50e9, np.nan), 2001: (52.5e9, 5.0), 2002: (55.125e9, 5.0), 2003: (np.nan, 5.0)},
            # small and fast: 100 -> 200 in three years
            "CCC": {2000: (1e9, np.nan), 2001: (1.26e9, 26.0), 2002: (1.5876e9, 26.0), 2003: (2.0e9, 25.97)},
        }
    )


def test_cagr_comes_from_levels_not_from_averaging_growth(toy):
    cagr = gg.window_cagr(toy, ["AAA"], 2000, 2003)["AAA"]
    assert cagr == pytest.approx((118.8 / 100) ** (1 / 3) * 100 - 100)  # 5.9105 %
    mean_growth = toy.loc["AAA", "growth"].dropna().mean()  # 6.667 %
    assert cagr < mean_growth


def test_window_uses_start_year_as_base(toy):
    table = gg.summary(toy, ["AAA"], 2000, 2003)
    row = table.iloc[0]
    assert row["years_with_data"] == 3 and row["years_expected"] == 3  # 2001, 2002, 2003
    assert row["mean_growth_pct"] == pytest.approx(20 / 3)
    # std of [10, -10, 20] with ddof=1: sqrt(466.67 / 2)
    assert row["volatility_pp"] == pytest.approx(15.2753, abs=1e-4)
    assert (row["recession_years"], row["worst_year"], row["worst_growth_pct"]) == (1, 2002, -10.0)
    assert (row["best_year"], row["best_growth_pct"]) == (2003, 20.0)


def test_shorter_window_drops_the_base_year_growth(toy):
    row = gg.summary(toy, ["AAA"], 2001, 2003).iloc[0]
    assert row["years_with_data"] == 2  # growth of 2002 and 2003 only
    assert row["mean_growth_pct"] == pytest.approx(5.0)
    assert row["cagr_pct"] == pytest.approx(((118.8 / 110) ** 0.5 - 1) * 100)


def test_missing_end_level_gives_nan_cagr_but_keeps_growth_stats(toy):
    row = gg.summary(toy, ["BBB"], 2000, 2003).iloc[0]
    assert np.isnan(row["cagr_pct"])
    assert row["mean_growth_pct"] == pytest.approx(5.0)
    assert row["years_with_data"] == 3


def test_unknown_country_is_reported_empty_not_crashing(toy):
    row = gg.summary(toy, ["ZZZ"], 2000, 2003).iloc[0]
    assert np.isnan(row["cagr_pct"]) and row["years_with_data"] == 0 and row["recession_years"] == 0


def test_invalid_window_raises(toy):
    with pytest.raises(ValueError):
        gg.window_cagr(toy, ["AAA"], 2003, 2003)


def test_rank_economies_orders_by_cagr_and_applies_size_filter(toy):
    full = gg.rank_economies(toy, 2000, 2003)
    assert list(full["iso3"]) == ["CCC", "AAA"]  # BBB has no end level; CCC grows 26% a year
    assert list(full["rank"]) == [1, 2] and set(full["ranked_of"]) == {2}
    # AAA is tiny (100 in constant US$) and CCC is $1bn: a $1bn floor keeps only CCC
    filtered = gg.rank_economies(toy, 2000, 2003, min_start_level_bn=1)
    assert list(filtered["iso3"]) == ["CCC"]


def test_rebased_levels_start_at_100(toy):
    out = gg.rebased_levels(toy, ["AAA"], 2000, 2003)
    assert list(out["year"]) == [2000, 2001, 2002, 2003]
    assert list(out["index"]) == pytest.approx([100.0, 110.0, 99.0, 118.8])


def test_decade_table_needs_enough_years():
    rows = {"AAA": {y: (1.0, 2.0) for y in range(1990, 2000)}}
    rows["AAA"].update({2000: (1.0, 4.0), 2001: (1.0, 6.0)})  # only two years of the 2000s
    table = gg.decade_table(make_frame(rows), ["AAA"])
    assert table.loc["1990s", "AAA"] == pytest.approx(2.0)
    assert np.isnan(table.loc["2000s", "AAA"])
    assert gg.decade_table(make_frame(rows), ["AAA"], min_obs=2).loc["2000s", "AAA"] == pytest.approx(5.0)


def test_recession_table_and_helper(toy):
    table = gg.recession_table(toy, ["AAA", "BBB"], 2000, 2003, {"AAA": "Alpha", "BBB": "Beta"})
    assert table.to_dict("records") == [{"country": "Alpha", "iso3": "AAA", "year": 2002, "growth_pct": -10.0}]
    assert gg.recession_years(pd.Series([1.0, -0.5, 0.0, -2.0], index=[1, 2, 3, 4])) == [2, 4]  # zero is not a recession


def test_coverage_counts_years_inside_window(toy):
    cov = gg.coverage(toy, ["AAA", "BBB"], 2001, 2003).set_index("country")
    assert cov.loc["AAA", "first_year"] == 2001 and cov.loc["AAA", "years_in_window"] == 2
    assert cov.loc["BBB", "years_expected"] == 2


def test_last_full_year_ignores_thinly_reported_years():
    rows = {f"C{i}": {2020: (1.0, 1.0), 2021: (1.0, 1.0)} for i in range(10)}
    for i in range(3):  # only 3 of 10 report 2022
        rows[f"C{i}"][2022] = (1.0, 1.0)
    assert gg.last_full_year(make_frame(rows)) == 2021


# --- sanity checks against the cached World Bank data -------------------------------------------------


@pytest.fixture(scope="module")
def real():
    return gg.load("GDP")


def test_real_data_coverage_floor(real):
    cov = gg.world_coverage(real)
    assert cov["economies"] >= 200
    assert cov["first_year"] <= 1961 and cov["last_year"] >= 2024
    assert 2023 <= cov["last_full_year"] <= cov["last_year"]


def test_real_growth_matches_level_changes(real):
    levels = real["level"].unstack("iso3")
    implied = (levels / levels.shift(1) - 1) * 100
    gap = (implied - real["growth"].unstack("iso3")).abs().stack()
    assert gap.max() < 1e-6  # the World Bank growth series is derived from the same constant-price levels


def test_real_usa_cagr_matches_hand_calculation(real):
    # World Bank levels: 13,717,679,619,695 (2000) and 22,731,468,331,926 (2024), constant 2015 US$
    expected = ((22_731_468_331_925.1 / 13_717_679_619_695.1) ** (1 / 24) - 1) * 100
    assert expected == pytest.approx(2.1267, abs=1e-4)
    assert gg.window_cagr(real, ["USA"], 2000, 2024)["USA"] == pytest.approx(expected, rel=1e-9)


def test_real_recession_years_for_usa_and_world_in_2020(real):
    window = gg.growth_in_window(real, ["USA"], 2000, 2024)["USA"].dropna()
    assert gg.recession_years(window) == [2009, 2020]
    negative, reporting = gg.share_in_recession(real, 2020)
    assert reporting >= 200 and negative / reporting > 0.7


def test_real_ranking_is_sorted_and_china_ranks_near_the_top(real):
    ranking = gg.rank_economies(real, 2000, 2024, min_start_level_bn=10)
    assert ranking["cagr_pct"].is_monotonic_decreasing
    assert ranking["start_level_bn"].min() >= 10
    assert ranking.set_index("iso3").loc["CHN", "rank"] <= 3


def test_per_capita_measure_loads(real):
    pc = gg.load("GDP per capita")
    assert pc.index.get_level_values("iso3").nunique() >= 200
    assert gg.window_cagr(pc, ["IND"], 2000, 2024)["IND"] < gg.window_cagr(real, ["IND"], 2000, 2024)["IND"]
