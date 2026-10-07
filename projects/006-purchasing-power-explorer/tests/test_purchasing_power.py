"""Unit tests for purchasing_power: synthetic data with hand-computed answers, plus checks on the cached data."""

import numpy as np
import pandas as pd
import pytest

import purchasing_power as pp

# ---------------------------------------------------------------- price level and conversion


def test_price_level_formula():
    assert pp.price_level(50, 100) == pytest.approx(50.0)
    assert pp.price_level(1, 1) == pytest.approx(100.0)  # the US: PPP factor and exchange rate are both 1
    series = pp.price_level(pd.Series([20.0, 100.0]), pd.Series([80.0, 100.0]))
    assert series.tolist() == pytest.approx([25.0, 100.0])


def test_ppp_valuation_sign():
    assert pp.ppp_valuation(50.0) == pytest.approx(-0.5)
    assert pp.ppp_valuation(125.0) == pytest.approx(0.25)
    assert pp.ppp_valuation(100.0) == pytest.approx(0.0)


def test_convert_hand_computed():
    # 20 local units buy what US$1 buys in the US; the market rate is 80 per dollar.
    c = pp.convert(100, ppp=20, fx=80)
    assert c.market_lcu == pytest.approx(8000)  # 100 x 80
    assert c.ppp_lcu == pytest.approx(2000)  # 100 x 20
    assert c.purchasing_power == pytest.approx(400)  # 8000 / 20
    assert c.multiplier == pytest.approx(4.0)


def test_convert_multiplier_is_100_over_price_level():
    ppp, fx = 7.3, 11.9
    assert pp.convert(250, ppp, fx).multiplier == pytest.approx(100 / pp.price_level(ppp, fx))


def test_convert_is_neutral_where_ppp_equals_market_rate():
    c = pp.convert(100, ppp=1.0, fx=1.0)
    assert c.market_lcu == c.ppp_lcu == c.purchasing_power == 100


@pytest.mark.parametrize("args", [(-1, 1, 1), (10, 0, 1), (10, 1, 0), (10, -1, 1)])
def test_convert_rejects_bad_input(args):
    with pytest.raises(ValueError):
        pp.convert(*args)


def test_big_macs():
    assert pp.big_macs(100, 5.0) == pytest.approx(20.0)
    with pytest.raises(ValueError):
        pp.big_macs(100, 0)


# ---------------------------------------------------------------- synthetic panel helpers


def make_panel(rows):
    frame = pd.DataFrame(rows, columns=["iso3", "country", "year", "price_level", "price_level_published", "gdp_nominal", "gdp_ppp"])
    frame["consistent"] = (frame["price_level"] - frame["price_level_published"]).abs() <= pp.CONSISTENCY_TOLERANCE
    return frame


def test_latest_complete_year_ignores_thin_recent_years():
    rows = [(f"C{i}", f"C{i}", y, 50.0, 50.0, 1.0, 1.0) for y in (2020, 2021) for i in range(10)]
    rows += [(f"C{i}", f"C{i}", 2022, 50.0, 50.0, 1.0, 1.0) for i in range(5)]
    assert pp.latest_complete_year(make_panel(rows)) == 2021


def test_consistency_report_flags_disagreement_and_ignores_missing():
    panel = make_panel(
        [
            ("AAA", "Alpha", 2020, 50.0, 50.4, 1, 1),  # within 1 point
            ("BBB", "Beta", 2020, 25.0, 49.0, 1, 1),  # unit mismatch
            ("CCC", "Gamma", 2020, 80.0, np.nan, 1, 1),  # no published value: not counted
        ]
    )
    rep = pp.consistency_report(panel)
    assert rep["n"] == 2
    assert rep["share_consistent"] == pytest.approx(0.5)
    assert rep["offenders"].to_dict() == {"Beta": 1}
    assert panel["consistent"].tolist() == [True, False, False]


def test_income_identity_gap_is_zero_when_incomes_agree_with_price_level():
    # nominal 1,000, PPP 4,000: ratio 4 = 100 / 25.
    panel = make_panel([("AAA", "Alpha", 2020, 25.0, 25.0, 1000.0, 4000.0), ("BBB", "Beta", 2020, 50.0, 50.0, 1000.0, 3000.0)])
    gap = pp.income_identity_gap(panel)
    assert gap.iloc[0] == pytest.approx(0.0)
    assert gap.iloc[1] == pytest.approx(0.5)  # ratio 3 against the implied 2


def test_income_table_ratio_and_filtering():
    panel = make_panel([("AAA", "Alpha", 2020, 25.0, 25.0, 1000.0, 4000.0), ("BBB", "Beta", 2020, 50.0, 50.0, np.nan, 3000.0), ("CCC", "Gamma", 2020, 80.0, 80.0, 500.0, 600.0)])
    table = pp.income_table(panel, 2020).set_index("iso3")
    assert list(table.index) == ["AAA", "CCC"]  # Beta has no nominal income
    assert table.loc["AAA", "ppp_over_nominal"] == pytest.approx(4.0)
    assert list(pp.income_table(panel, 2020, ["CCC"])["iso3"]) == ["CCC"]


def test_crosscheck_uses_only_consistent_rows():
    panel = make_panel([("AAA", "Alpha", 2020, 40.0, 40.0, 1, 1), ("BBB", "Beta", 2020, 20.0, 60.0, 1, 1), ("CCC", "Gamma", 2020, 90.0, 90.0, 1, 1)])
    annual = pd.DataFrame({"iso3": ["AAA", "BBB", "CCC", "AAA"], "year": [2020, 2020, 2020, 2019], "bigmac_level": [60.0, 30.0, 135.0, 55.0]})
    merged = pp.crosscheck_bigmac(panel, 2020, annual).set_index("iso3")
    assert list(merged.index) == ["AAA", "CCC"]  # Beta is flagged, and the 2019 row is a different year
    assert merged.loc["AAA", "ratio"] == pytest.approx(1.5)
    assert merged.loc["CCC", "ratio"] == pytest.approx(1.5)
    assert pp.crosscheck_summary(merged.reset_index())["median_ratio"] == pytest.approx(1.5)


# ---------------------------------------------------------------- Penn effect


def power_law_sample(slope, intercept, n=60, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    income = np.geomspace(1_000, 100_000, n)
    level = np.exp(intercept + slope * np.log(income) + rng.normal(0, noise, n))
    return pd.DataFrame({"price_level": level, "gdp_ppp": income})


def test_penn_fit_recovers_exact_power_law():
    fit = pp.penn_fit(power_law_sample(0.25, np.log(10)))
    assert fit.slope == pytest.approx(0.25)
    assert fit.intercept == pytest.approx(np.log(10))
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.n == 60
    assert fit.predict([1000.0, 10000.0]).tolist() == pytest.approx([10 * 1000**0.25, 10 * 10000**0.25])
    assert fit.ten_percent_effect == pytest.approx((1.1**0.25 - 1) * 100)


def test_penn_fit_with_noise_brackets_the_truth():
    fit = pp.penn_fit(power_law_sample(0.3, 0.5, n=200, noise=0.3, seed=4))
    lo, hi = fit.ci95
    assert lo < 0.3 < hi
    assert 0 < fit.r_squared < 1
    assert fit.p_value < 0.001
    assert fit.slope_se > 0


def test_penn_fit_slope_matches_numpy_polyfit():
    sample = power_law_sample(0.2, 1.0, n=80, noise=0.4, seed=1)
    expected = np.polyfit(np.log(sample["gdp_ppp"]), np.log(sample["price_level"]), 1)
    fit = pp.penn_fit(sample)
    assert (fit.slope, fit.intercept) == pytest.approx(tuple(expected))


def test_penn_fit_needs_enough_countries():
    with pytest.raises(ValueError):
        pp.penn_fit(power_law_sample(0.2, 1.0, n=5))


def test_penn_sample_filters():
    panel = make_panel(
        [
            ("AAA", "Alpha", 2020, 40.0, 40.0, 1000.0, 4000.0),
            ("BBB", "Beta", 2020, 20.0, 60.0, 1000.0, 3000.0),  # inconsistent
            ("CCC", "Gamma", 2020, 90.0, 90.0, 500.0, -1.0),  # impossible income
            ("DDD", "Delta", 2020, 70.0, 70.0, 900.0, np.nan),  # missing income
            ("EEE", "Epsilon", 2021, 70.0, 70.0, 900.0, 5000.0),  # other year
        ]
    )
    assert list(pp.penn_sample(panel, 2020).index) == ["AAA"]


# ---------------------------------------------------------------- cached World Bank and Big Mac data


@pytest.fixture(scope="module")
def panel():
    return pp.build_panel()


def test_panel_coverage(panel):
    assert panel["iso3"].nunique() > 200
    assert panel["year"].min() <= 1990 and panel["year"].max() >= 2024
    assert pp.latest_complete_year(panel) >= 2023
    assert panel["price_level"].notna().sum() > 6000


def test_us_price_level_is_exactly_100(panel):
    usa = panel[(panel["iso3"] == "USA") & panel["price_level"].notna()]
    assert len(usa) >= 30
    assert (usa["price_level"] - 100).abs().max() < 1e-9


def test_india_price_level_by_hand(panel):
    # India 2024: PPP factor about 20.45 rupees per international dollar, exchange rate about 83.67 per US dollar.
    # 20.45 / 83.67 x 100 = 24.44; one dollar buys about 4.1 times what it buys in the US.
    india = pp.year_slice(panel, 2024).loc["IND"]
    assert india["price_level"] == pytest.approx(20.45 / 83.67 * 100, abs=0.05)
    assert india["price_level"] == pytest.approx(india["price_level_published"], abs=pp.CONSISTENCY_TOLERANCE)  # published: 24.18
    assert india["consistent"]
    assert pp.convert(100, india["ppp"], india["fx"]).multiplier == pytest.approx(4.09, abs=0.02)


def test_own_price_level_matches_published_index_for_most_country_years(panel):
    rep = pp.consistency_report(panel)
    assert rep["n"] > 6000
    assert 0.85 < rep["share_consistent"] < 1.0
    assert {"Bulgaria", "Croatia", "Liberia"} <= set(rep["offenders"].head(10).index)


def test_bulgaria_mismatch_is_a_currency_unit_gap(panel):
    # Own and published values differ by about 1.96, the lev/euro rate: PPP is in euros, the exchange rate in leva.
    bgr = panel[(panel["iso3"] == "BGR") & (panel["year"].between(2000, 2020))]
    ratio = (bgr["price_level_published"] / bgr["price_level"]).median()
    assert ratio == pytest.approx(1.95583, abs=0.01)
    assert not bgr["consistent"].any()


def test_income_identity_holds_in_recent_years(panel):
    recent = panel[panel["consistent"] & (panel["year"] == 2024)]
    gap = pp.income_identity_gap(recent)
    assert len(gap) > 150
    assert (gap.abs() < 0.01).mean() > 0.95


def test_india_income_by_hand(panel):
    table = pp.income_table(panel, 2024, ["IND"]).iloc[0]
    # about 10,719 PPP dollars against 2,592 nominal dollars
    assert table["ppp_over_nominal"] == pytest.approx(table["gdp_ppp"] / table["gdp_nominal"])
    assert table["ppp_over_nominal"] == pytest.approx(100 / table["price_level"], rel=0.02)
    assert 4.0 < table["ppp_over_nominal"] < 4.3


def test_bigmac_releases_are_relative_to_us_and_match_the_economists_index():
    releases = pp.bigmac_releases()
    assert "EUZ" not in set(releases["iso3"])
    assert releases.loc[releases["iso3"] == "USA", "bigmac_level"].eq(100).all()
    # USD_raw is the Economist's own over/undervaluation: price relative to the US, minus 1.
    assert ((releases["bigmac_level"] / 100 - 1) - releases["USD_raw"]).abs().max() < 1e-4
    annual = pp.bigmac_annual(releases)
    assert annual["year"].min() == 2000 and annual["iso3"].nunique() > 50


def test_crosscheck_with_big_mac(panel):
    merged = pp.crosscheck_bigmac(panel, 2024)
    stats = pp.crosscheck_summary(merged)
    assert stats["n"] > 40
    assert stats["spearman"] > 0.6
    assert 1.0 < stats["median_ratio"] < 2.0  # the Big Mac is dearer than the broad basket in poorer countries
    by_year = pp.crosscheck_by_year(panel, range(2010, 2025))
    assert (by_year["spearman"] > 0.5).all() and len(by_year) == 15


def test_penn_effect_on_real_data(panel):
    year = pp.latest_complete_year(panel)
    sample = pp.penn_sample(panel, year)
    fit = pp.penn_fit(sample)
    assert fit.n > 150
    assert 0.1 < fit.slope < 0.3
    assert fit.p_value < 1e-6
    assert 0.1 < fit.r_squared < 0.6
    # Check against a plain least-squares fit done another way.
    slope, _ = np.polyfit(np.log(sample["gdp_ppp"]), np.log(sample["price_level"]), 1)
    assert fit.slope == pytest.approx(slope)


def test_penn_slope_is_positive_and_significant_every_year_since_2000(panel):
    yearly = pp.penn_by_year(panel, first_year=2000)
    assert len(yearly) >= 24
    assert (yearly["slope"] - 1.96 * yearly["se"] > 0).all()
    assert yearly["n"].min() > 100


def test_regions_cover_the_panel(panel):
    region = pp.regions()
    assert region["IND"] == "South Asia"
    assert set(pp.year_slice(panel, 2024).index) <= set(region.index) | set(panel["iso3"])
