"""Unit tests for gini_calc. Expected values are worked out by hand in the comments."""

import io

import numpy as np
import pytest

import gini_calc as gc
from core import inequality as ineq


# ---------------------------------------------------------------- parsing


def test_parse_numbers_accepts_mixed_separators():
    data = gc.parse_numbers("1, 2;3\n4   5")
    assert data.values.tolist() == [1, 2, 3, 4, 5]
    assert data.weights is None


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("", "No numbers found"),
        ("   \n ", "No numbers found"),
        ("5", "at least 2"),
        ("1 2 abc", "'abc'"),
        ("1 2 x y", "2 entries are not numbers"),
        ("1 -2 3", "Negative values"),
        ("0 0 0", "All values are zero"),
        ("1 2 nan", "finite"),
        ("1 2 inf", "finite"),
    ],
)
def test_parse_numbers_errors_say_what_is_wrong(text, fragment):
    with pytest.raises(gc.InputError, match=fragment):
        gc.parse_numbers(text)


def test_negative_error_names_the_row():
    with pytest.raises(gc.InputError, match=r"row\(s\) 3"):
        gc.validate([5, 6, -1, 7])


def test_input_error_is_a_value_error():
    assert issubclass(gc.InputError, ValueError)


def test_parse_csv_with_weights_matches_duplication():
    text = "income,weight\n1,3\n5,1\n"
    data = gc.parse_csv(text)
    assert (data.value_column, data.weight_column) == ("income", "weight")
    assert ineq.gini(data.values, data.weights) == pytest.approx(ineq.gini([1, 1, 1, 5]))


def test_parse_csv_accepts_bytes_and_other_delimiters():
    data = gc.parse_csv(b"income;weight\n10;1\n20;2\n30;1\n")
    assert data.values.tolist() == [10, 20, 30]
    assert data.weights.tolist() == [1, 2, 1]


def test_parse_csv_headerless_numbers():
    data = gc.parse_csv("10\n20\n30\n")
    assert data.values.tolist() == [10, 20, 30]


def test_parse_csv_first_numeric_column_when_no_hint():
    data = gc.parse_csv("household,amount\nA,100\nB,300\n")
    assert data.value_column == "amount"
    assert data.values.tolist() == [100, 300]


def test_parse_csv_explicit_columns():
    data = gc.parse_csv("a,b,c\n1,10,2\n2,20,1\n", value_column="b", weight_column="c")
    assert data.values.tolist() == [10, 20]
    assert data.weights.tolist() == [2, 1]


def test_parse_csv_accepts_file_like():
    assert gc.parse_csv(io.StringIO("income\n1\n2\n")).values.tolist() == [1, 2]


def test_parse_csv_errors():
    with pytest.raises(gc.InputError, match="'wage' not found.*income, weight"):
        gc.parse_csv("income,weight\n1,1\n2,1\n", value_column="wage")
    with pytest.raises(gc.InputError, match=r"not a number in file row\(s\) 3"):
        gc.parse_csv("income\n1\nabc\n3\n")
    with pytest.raises(gc.InputError, match=r"empty in file row\(s\) 3"):
        gc.parse_csv("income,weight\n1,1\n2,\n3,1\n")
    with pytest.raises(gc.InputError, match="Weights must be positive"):
        gc.parse_csv("income,weight\n1,1\n2,0\n")
    with pytest.raises(gc.InputError, match="No numeric column"):
        gc.parse_csv("name,city\nA,X\nB,Y\n")
    with pytest.raises(gc.InputError, match="no data rows"):
        gc.parse_csv("income\n")


def test_validate_weight_length_mismatch():
    with pytest.raises(gc.InputError, match="3 values but 2 weights"):
        gc.validate([1, 2, 3], [1, 1])


# ---------------------------------------------------------------- bootstrap


def test_bootstrap_is_reproducible_and_seed_dependent():
    x = gc.lognormal_sample(300, 0.8, seed=5)
    a = gc.bootstrap_gini(x, n_boot=200, seed=1)
    b = gc.bootstrap_gini(x, n_boot=200, seed=1)
    c = gc.bootstrap_gini(x, n_boot=200, seed=2)
    assert a == b
    assert (a.low, a.high) != (c.low, c.high)
    assert a.gini == c.gini == pytest.approx(ineq.gini(x))


def test_bootstrap_interval_brackets_estimate_and_narrows_with_n():
    small = gc.bootstrap_gini(gc.lognormal_sample(100, 0.8, seed=3), n_boot=300)
    large = gc.bootstrap_gini(gc.lognormal_sample(3000, 0.8, seed=3), n_boot=300)
    assert small.low < small.gini < small.high
    assert large.low < large.gini < large.high
    assert large.half_width < small.half_width / 3


def test_bootstrap_higher_level_is_wider():
    x = gc.lognormal_sample(200, 0.8, seed=9)
    narrow = gc.bootstrap_gini(x, level=0.80, n_boot=400)
    wide = gc.bootstrap_gini(x, level=0.99, n_boot=400)
    assert wide.half_width > narrow.half_width


def test_bootstrap_respects_weights():
    # Weights 3 and 1 are the same population as [1, 1, 1, 5], so the point estimate agrees.
    est = gc.bootstrap_gini([1, 5], [3, 1], n_boot=50)
    assert est.gini == pytest.approx(ineq.gini([1, 1, 1, 5]))


def test_bootstrap_rejects_bad_arguments():
    with pytest.raises(ValueError):
        gc.bootstrap_gini([1, 2, 3], level=1.5)
    with pytest.raises(ValueError):
        gc.bootstrap_gini([1, 2, 3], n_boot=1)
    with pytest.raises(gc.InputError):
        gc.bootstrap_gini([1, -2, 3])


def test_bootstrap_handles_resamples_of_all_zeros():
    # Three zeros and one positive value: some resamples contain only zeros and are skipped.
    est = gc.bootstrap_gini([0, 0, 0, 7], n_boot=200)
    assert 0.0 <= est.low <= est.high <= 1.0


def test_bootstrap_coverage_is_reasonable_for_moderate_samples():
    assert gc.bootstrap_coverage(200, reps=40, n_boot=100) > 0.80


# ---------------------------------------------------------------- grouped data


def test_equal_shares_give_zero_gini():
    assert gc.gini_from_shares([20, 20, 20, 20, 20]) == pytest.approx(0.0)


def test_all_income_in_top_group():
    # Lorenz points (0,0) (.2,0) (.4,0) (.6,0) (.8,0) (1,1): area = .2 * 1/2 = .1, so G = 1 - 2(.1) = .8 = 1 - 1/5.
    assert gc.gini_from_shares([0, 0, 0, 0, 1]) == pytest.approx(0.8)
    assert gc.gini_from_shares([0] * 9 + [1]) == pytest.approx(0.9)


def test_grouped_gini_hand_computed_quintiles():
    # Cumulative shares .10 .25 .45 .70 1.00 -> area = .2 * (.05 + .175 + .35 + .575 + .85) = .4, G = 1 - .8 = .2.
    assert gc.gini_from_shares([0.10, 0.15, 0.20, 0.25, 0.30]) == pytest.approx(0.2)


def test_grouped_gini_is_exact_when_each_person_is_a_group():
    # Incomes 1,2,3,4 as four groups: the textbook Gini of 0.25 is recovered exactly.
    assert gc.gini_from_shares([1, 2, 3, 4]) == pytest.approx(0.25)


def test_shares_accept_percentages_and_rounding():
    assert gc.gini_from_shares([10, 15, 20, 25, 30]) == pytest.approx(0.2)
    # World Bank shares are rounded and can sum to 99.8: they are rescaled rather than rejected.
    assert gc.gini_from_shares([10.0, 15.0, 20.0, 25.0, 29.8]) == pytest.approx(0.2, abs=0.005)


def test_lorenz_from_shares_points():
    pop, inc = gc.lorenz_from_shares([10, 15, 20, 25, 30])
    assert pop.tolist() == pytest.approx([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    assert inc.tolist() == pytest.approx([0, 0.10, 0.25, 0.45, 0.70, 1.0])


@pytest.mark.parametrize(
    ("shares", "fragment"),
    [
        ([50], "at least 2"),
        ([10, -5, 95], "non-negative"),
        ([0, 0, 0], "sum to zero"),
        ([30, 10, 20, 15, 25], "ordered"),
        ([10, np.nan, 90], "non-negative"),
    ],
)
def test_bad_shares_are_rejected(shares, fragment):
    with pytest.raises(gc.InputError, match=fragment):
        gc.gini_from_shares(shares)


def test_grouped_gini_is_a_lower_bound_and_tightens_with_more_groups():
    x = gc.lognormal_sample(50_000, 1.0, seed=2)
    full = ineq.gini(x)
    five, ten, hundred = (gc.grouped_gini(x, groups=k) for k in (5, 10, 100))
    assert five < ten < hundred < full
    assert full - hundred < 0.002


def test_summary_of_known_data():
    s = gc.summarise(np.arange(1, 101), n_boot=100)
    assert s.n == 100
    assert s.shares.sum() == pytest.approx(1.0)
    assert s.gini.gini == pytest.approx(ineq.gini(np.arange(1, 101)))
    assert s.top10 == pytest.approx(ineq.top_share(np.arange(1, 101)))
    assert s.grouped_gini < s.gini.gini
    assert list(s.table()["Group"]) == gc.QUINTILE_LABELS


# ---------------------------------------------------------------- synthetic distributions


def test_lognormal_sample_matches_theory():
    assert ineq.gini(gc.lognormal_sample(200_000, 0.8)) == pytest.approx(gc.lognormal_gini(0.8), abs=0.005)


def test_pareto_sample_matches_theory():
    # Pareto type I: G = 1 / (2 alpha - 1); alpha = 3 gives 0.2.
    assert gc.pareto_gini(3) == pytest.approx(0.2)
    assert ineq.gini(gc.pareto_sample(300_000, 3.0)) == pytest.approx(0.2, abs=0.01)
    assert gc.pareto_sample(1000, 3.0).min() >= 10_000


def test_pareto_gini_needs_finite_mean():
    with pytest.raises(ValueError):
        gc.pareto_gini(1.0)


def test_samples_are_seeded():
    assert np.array_equal(gc.lognormal_sample(10, 0.5, seed=1), gc.lognormal_sample(10, 0.5, seed=1))
    assert not np.array_equal(gc.lognormal_sample(10, 0.5, seed=1), gc.lognormal_sample(10, 0.5, seed=2))


def test_lognormal_grouped_gap_matches_simulation_and_shrinks_with_groups():
    sim = ineq.gini(x := gc.lognormal_sample(300_000, 0.8, seed=4)) - gc.grouped_gini(x, groups=5)
    assert gc.lognormal_grouped_gap(gc.lognormal_gini(0.8)) == pytest.approx(sim, abs=0.002)
    assert gc.lognormal_grouped_gap(0.4, groups=10) < gc.lognormal_grouped_gap(0.4, groups=5)
    assert gc.lognormal_grouped_gap(0.0) == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------- World Bank data (cached, offline)


@pytest.fixture(scope="module")
def table():
    return gc.worldbank_table()


def test_worldbank_table_coverage(table):
    cov = gc.coverage(table)
    assert cov["country_years"] > 2000
    assert cov["countries"] > 150
    assert cov["first_year"] < 1990 and cov["last_year"] >= 2022
    assert table["iso3"].str.len().eq(3).all()
    assert not table.isna().any().any()


def test_worldbank_shares_are_sensible(table):
    shares = table[list(gc.WB_QUINTILES)]
    assert shares.sum(axis=1).between(99.5, 100.5).all()
    assert (shares.diff(axis=1).iloc[:, 1:] >= 0).all().all()  # quintile shares rise with income


def test_namibia_2015_by_hand(table):
    # Namibia 2015 shares 2.8, 5.8, 9.8, 17.9, 63.7 (% of income), published Gini 59.1.
    # Area = .2 * (c1 + c2 + c3 + c4 + .5) with cumulative shares c1..c4 = .028 .086 .184 .363, so G = 1 - 2 * area.
    c = np.cumsum([2.8, 5.8, 9.8, 17.9]) / 100
    by_hand = (1 - 0.4 * (c.sum() + 0.5)) * 100
    row = table[(table["iso3"] == "NAM") & (table["year"] == 2015)].iloc[0]
    assert by_hand == pytest.approx(53.56)
    assert row["gini_grouped"] == pytest.approx(by_hand, abs=0.05)  # shares sum to 100.0 here, so no rescaling
    assert row["gini_published"] == pytest.approx(59.1)
    assert row["gap"] == pytest.approx(59.1 - by_hand, abs=0.05)


def test_grouped_estimate_never_exceeds_published(table):
    # Lower-bound property on real data: every one of the country-years sits below the published Gini.
    assert (table["gap"] > 0).all()
    s = gc.understatement_summary(table)
    assert 1.5 < s["mean_gap"] < 4.5
    assert s["corr_gap_gini"] > 0.8


def test_lognormal_explains_most_of_the_gap(table):
    check = gc.lognormal_gap_check(gc.latest_per_country(table))
    assert check["corr"] > 0.9
    assert check["mean_abs_error"] < 1.0


def test_latest_per_country_has_one_row_each(table):
    latest = gc.latest_per_country(table)
    assert latest["iso3"].is_unique
    assert len(latest) == table["iso3"].nunique()
    for iso3 in ["USA", "BRA"]:
        assert latest.loc[latest["iso3"] == iso3, "year"].iloc[0] == table.loc[table["iso3"] == iso3, "year"].max()


def test_lorenz_for_country(table):
    pop, inc, year = gc.lorenz_for_country(table, "BRA")
    assert year == table.loc[table["iso3"] == "BRA", "year"].max()
    assert (pop[0], inc[0]) == (0.0, 0.0) and (pop[-1], inc[-1]) == (1.0, 1.0)
    assert (inc <= pop + 1e-12).all()
    _, _, first_year = gc.lorenz_for_country(table, "BRA", year=table.loc[table["iso3"] == "BRA", "year"].min())
    assert first_year < year
    with pytest.raises(KeyError):
        gc.lorenz_for_country(table, "ZZZ")
    with pytest.raises(KeyError):
        gc.lorenz_for_country(table, "BRA", year=1800)
