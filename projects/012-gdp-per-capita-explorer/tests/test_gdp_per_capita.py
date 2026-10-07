"""Unit tests for gdp_per_capita: hand-computed synthetic cases, then checks against the cached data."""

import math

import numpy as np
import pandas as pd
import pytest

import gdp_per_capita as gp


def frame(rows: dict[tuple[str, int], dict[str, float]]) -> pd.DataFrame:
    """Wide (iso3, year) frame with every series column present (NaN where not given)."""
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.MultiIndex.from_tuples(df.index, names=["iso3", "year"])
    for col in gp.SERIES:
        if col not in df:
            df[col] = np.nan
    return df.sort_index()


COUNTRIES = ["USA", "GBR", "DEU", "FRA", "ITA", "ESP"]  # real codes so names and regions resolve


def test_regression_hand_computed_slope_intercept_r2_and_robust_se():
    # ln(income) = 0..4 and life expectancy = 1, 3, 2, 5, 4.
    # Sxy = 8, Sxx = 10, Syy = 10: slope 0.8, intercept 3 - 0.8 * 2 = 1.4, R2 = 64 / 100.
    # Residuals -0.4, 0.8, -1, 1.2, -0.6; HC1 var(b) = 5/3 * sum((x - 2)^2 e^2) / Sxx^2 = 5/3 * 4.16 / 100.
    life = [1, 3, 2, 5, 4]
    rows = {(c, 2000): {"ppp": math.exp(k), "life_exp": life[k], "pop": 1.0} for k, c in enumerate(COUNTRIES[:5])}
    fit = gp.fit_preston(frame(rows), 2000)
    assert fit.n == 5
    assert fit.coef("ln_income") == pytest.approx(0.8)
    assert fit.coef("const") == pytest.approx(1.4)
    assert fit.r2 == pytest.approx(0.64)
    assert fit.se("ln_income") == pytest.approx(math.sqrt(5 / 3 * 4.16 / 100))


def test_preston_curve_predicts_the_fitted_line_and_curvature_term_is_optional():
    rows = {(c, 2000): {"ppp": math.exp(k + 1), "life_exp": 10 + 5 * (k + 1), "pop": 1.0} for k, c in enumerate(COUNTRIES)}
    df = frame(rows)
    fit = gp.fit_preston(df, 2000)
    assert fit.coef("ln_income") == pytest.approx(5.0) and fit.coef("const") == pytest.approx(10.0)
    assert gp.preston_curve(fit, [math.e**3])[0] == pytest.approx(25.0)
    quad = gp.fit_preston(df, 2000, curvature=True)
    assert "ln_income_sq" in quad.names and quad.coef("ln_income_sq") == pytest.approx(0.0, abs=1e-9)
    assert gp.preston_curve(quad, [math.e**3])[0] == pytest.approx(25.0)


def test_fit_preston_refuses_tiny_samples():
    rows = {("USA", 2000): {"ppp": 10.0, "life_exp": 70.0, "pop": 1.0}, ("GBR", 2000): {"ppp": 20.0, "life_exp": 75.0, "pop": 1.0}}
    with pytest.raises(ValueError):
        gp.fit_preston(frame(rows), 2000)


def test_preston_frame_drops_countries_missing_any_of_the_three_fields():
    rows = {
        ("USA", 2000): {"ppp": 10.0, "life_exp": 70.0, "pop": 5.0},
        ("GBR", 2000): {"ppp": 20.0, "life_exp": np.nan, "pop": 5.0},
        ("DEU", 2000): {"ppp": np.nan, "life_exp": 80.0, "pop": 5.0},
    }
    out = gp.preston_frame(frame(rows), 2000)
    assert list(out["iso3"]) == ["USA"] and out["region"].iloc[0] == "North America"


def convergence_frame() -> pd.DataFrame:
    """Five countries, ten years, growth = 5 - 0.5 * ln(initial income) per cent per year exactly."""
    rows = {}
    for k, c in enumerate(COUNTRIES[:5]):
        ln0 = 6 + k
        growth = 5 - 0.5 * ln0
        rows[(c, 2000)] = {"ppp": math.exp(ln0), "pop": float(10 * (k + 1))}
        rows[(c, 2010)] = {"ppp": math.exp(ln0 + growth / 100 * 10), "pop": float(10 * (k + 1))}
    return frame(rows)


def test_beta_convergence_recovers_known_negative_beta():
    reg, sample = gp.beta_convergence(convergence_frame(), 2000, 2010)
    assert reg.n == 5
    assert reg.coef("ln_initial") == pytest.approx(-0.5)  # poorer countries grew faster
    assert reg.coef("const") == pytest.approx(5.0)
    assert sorted(sample["growth"].round(6)) == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_beta_convergence_population_filter_and_weights():
    df = convergence_frame()
    reg, sample = gp.beta_convergence(df, 2000, 2010, min_population=20)
    assert reg.n == 4 and "USA" not in set(sample["iso3"])  # USA has population 10
    weighted, _ = gp.beta_convergence(df, 2000, 2010, weighted=True)
    assert weighted.coef("ln_initial") == pytest.approx(-0.5)  # an exact line is fitted by any weights
    with pytest.raises(ValueError):
        gp.beta_convergence(df, 2010, 2000)


def test_convergence_speed_hand_computed():
    # beta = -0.5 pp per log point, T = 10: b = -0.005, lambda = -ln(0.95) / 10 = 0.0051293, half-life = ln 2 / lambda = 135.1 years.
    rate, half_life = gp.convergence_speed(-0.5, 10)
    assert rate == pytest.approx(0.0051293, abs=1e-6) and half_life == pytest.approx(135.1, abs=0.1)
    assert gp.convergence_speed(0.2, 10) is None  # divergence: no half-life
    assert gp.convergence_speed(0.0, 10) is None
    assert gp.convergence_speed(-20.0, 10) is None  # 1 + b * T <= 0 is outside the model


def test_convergence_by_window_reports_each_window():
    rows = {}
    for k, c in enumerate(COUNTRIES[:5]):
        ln0 = 6 + k
        for year, level in {2000: ln0, 2005: ln0 + (5 - 0.5 * ln0) / 100 * 5, 2010: ln0 + (5 - 0.5 * ln0) / 100 * 10}.items():
            rows[(c, year)] = {"ppp": math.exp(level), "pop": 1.0}
    out = gp.convergence_by_window(frame(rows), [(2000, 2005), (2000, 2010)])
    assert list(out["window"]) == ["2000-2005", "2000-2010"]
    assert out["n"].tolist() == [5, 5] and (out["beta"].round(6) == -0.5).all()


def test_weighted_gini_hand_computed():
    # Two countries, incomes 1 and 9, populations 1 and 3 (the rich one is bigger).
    # Income held: 1 x 1 = 1 and 9 x 3 = 27, so income shares are 1/28 and 27/28 for population shares 0.25 and 0.75.
    # Lorenz points (0,0), (0.25, 1/28), (1, 1): area = 0.25/56 + 0.75 x (29/28)/2 = 11/28, so G = 1 - 22/28 = 3/14.
    # Cross-check with the pairwise formula: 2 x 0.25 x 0.75 x |9 - 1| / (2 x mean 7) = 3/14.
    # Unweighted (equal weights): Lorenz (0,0), (0.5, 0.1), (1, 1): area 0.025 + 0.275 = 0.3, so G = 0.4.
    rows = {("USA", 2000): {"ppp": 9.0, "pop": 3.0}, ("GBR", 2000): {"ppp": 1.0, "pop": 1.0}, ("DEU", 2000): {"pop": 4.0}}
    out = gp.weighted_gini_by_year(frame(rows)).set_index("year")
    assert out.loc[2000, "gini_weighted"] == pytest.approx(3 / 14)
    assert out.loc[2000, "gini_unweighted"] == pytest.approx(0.4)
    assert out.loc[2000, "n"] == 2
    assert out.loc[2000, "pop_share_covered"] == pytest.approx(4 / 8)  # Germany's 4 of 8 people have no income figure


def test_weighted_gini_exclude_removes_countries_from_everything():
    rows = {("USA", 2000): {"ppp": 9.0, "pop": 3.0}, ("GBR", 2000): {"ppp": 1.0, "pop": 1.0}, ("DEU", 2000): {"ppp": 5.0, "pop": 2.0}}
    full = gp.weighted_gini_by_year(frame(rows)).iloc[0]
    reduced = gp.weighted_gini_by_year(frame(rows), exclude=["DEU"]).iloc[0]
    assert full["n"] == 3 and reduced["n"] == 2
    assert reduced["gini_weighted"] == pytest.approx(3 / 14)  # same two countries as the hand-computed case
    assert reduced["pop_share_covered"] == pytest.approx(1.0)  # the excluded country is not counted as missing


def test_comparison_table_keeps_gaps_and_unknown_countries():
    rows = {("USA", 2020): {"ppp": 70000.0, "life_exp": 77.0, "pop": 330e6, "electricity": np.nan}, ("GBR", 2020): {"ppp": 50000.0}}
    out = gp.comparison_table(frame(rows), ["GBR", "USA", "XXX"], 2020)
    assert list(out["iso3"]) == ["GBR", "USA", "XXX"]
    assert out.loc[1, "country"] == "United States" and out.loc[1, "ppp"] == 70000.0
    assert pd.isna(out.loc[0, "life_exp"]) and pd.isna(out.loc[2, "ppp"]) and pd.isna(out.loc[1, "electricity"])


def test_latest_common_year_requires_every_column_to_be_broad():
    rows = {}
    for year, n_ppp, n_le in [(2000, 10, 10), (2001, 10, 10), (2002, 10, 4), (2003, 3, 10)]:
        for i in range(10):
            rows[(f"C{i:02d}", year)] = {"ppp": 1.0 if i < n_ppp else np.nan, "life_exp": 1.0 if i < n_le else np.nan}
    df = frame(rows)
    assert gp.latest_common_year(df, ["ppp", "life_exp"]) == 2001  # 2002 is thin for life expectancy, 2003 for income
    assert gp.latest_common_year(df, ["life_exp"]) == 2003


def test_coverage_reports_years_and_countries():
    rows = {("USA", 2000): {"ppp": 1.0}, ("USA", 2001): {"ppp": 2.0}, ("GBR", 2001): {"ppp": 3.0}}
    cov = gp.coverage(frame(rows)).set_index("series")
    row = cov.loc[gp.LABELS["ppp"]]
    assert (row["first_year"], row["last_year"], row["countries"], row["best_year"], row["countries_in_best_year"]) == (2000, 2001, 2, 2001, 2)


# ----------------------------------------------------------------------------- real cached data


@pytest.fixture(scope="module")
def real() -> pd.DataFrame:
    return gp.load()


def pairwise_gini(x: np.ndarray, w: np.ndarray) -> float:
    """Independent Gini: sum_ij w_i w_j |x_i - x_j| / (2 W^2 mean)."""
    mean = (x * w).sum() / w.sum()
    return float((w[:, None] * w[None, :] * np.abs(x[:, None] - x[None, :])).sum() / (2 * w.sum() ** 2 * mean))


def test_real_data_has_every_series_and_expected_coverage(real):
    assert set(real.columns) == set(gp.SERIES)
    cov = gp.coverage(real).set_index("series")
    assert cov.loc[gp.LABELS["ppp"], "first_year"] == 1990 and cov.loc[gp.LABELS["ppp"], "countries"] >= 190
    assert cov.loc[gp.LABELS["electricity"], "countries"] >= 140
    assert cov.loc[gp.LABELS["co2_pc"], "countries"] >= 190
    assert gp.latest_common_year(real, ["ppp", "life_exp", "pop"]) == 2024
    assert gp.latest_common_year(real, gp.TABLE_COLUMNS) == 2023


def test_real_preston_fit_matches_independent_numpy_polyfit(real):
    for year, n in [(1990, 185), (2024, 195)]:
        sub = gp.preston_frame(real, year)
        slope, intercept = np.polyfit(np.log(sub["ppp"]), sub["life_exp"], 1)
        fit = gp.fit_preston(real, year)
        assert fit.n == n == len(sub)
        assert fit.coef("ln_income") == pytest.approx(slope) and fit.coef("const") == pytest.approx(intercept)
    # Values quoted in the README.
    assert gp.fit_preston(real, 1990).coef("ln_income") == pytest.approx(6.44, abs=0.01)
    assert gp.fit_preston(real, 2024).coef("ln_income") == pytest.approx(5.26, abs=0.01)
    assert 0.6 < gp.fit_preston(real, 1990).r2 < 0.7 and 0.7 < gp.fit_preston(real, 2024).r2 < 0.8


def test_real_richer_countries_live_longer_in_every_year(real):
    over = gp.preston_over_time(real, 1990, 2024)
    assert len(over) == 35
    assert (over["slope"] > 4).all() and (over["slope"] / over["slope_se"] > 10).all()
    # The whole curve has shifted up: at $5,000 the fit predicts more years of life in 2024 than in 1990.
    old, new = (gp.preston_curve(gp.fit_preston(real, y), [5000])[0] for y in (1990, 2024))
    assert new - old > 5


def test_real_beta_convergence_1990_2024(real):
    reg, sample = gp.beta_convergence(real, 1990, 2024)
    slope, _ = np.polyfit(sample["ln_initial"], sample["growth"], 1)
    assert reg.n == len(sample) == 183
    assert reg.coef("ln_initial") == pytest.approx(slope)
    assert reg.coef("ln_initial") == pytest.approx(-0.395, abs=0.001)
    assert reg.se("ln_initial") == pytest.approx(0.108, abs=0.001)
    assert reg.p("ln_initial") < 0.001
    big, _ = gp.beta_convergence(real, 1990, 2024, min_population=1e6)
    assert big.n == 139 and big.coef("ln_initial") < 0
    heavy, _ = gp.beta_convergence(real, 1990, 2024, weighted=True)
    assert heavy.coef("ln_initial") < -1.0  # weighting by population (China, India) strengthens convergence


def test_real_convergence_is_not_significant_in_the_1990s(real):
    windows = gp.convergence_by_window(real, [(1990, 2000), (2000, 2010)]).set_index("window")
    assert windows.loc["1990-2000", "p_value"] > 0.1
    assert windows.loc["2000-2010", "p_value"] < 0.01


def test_real_weighted_gini_1990_vs_2024_matches_independent_formula(real):
    g = gp.weighted_gini_by_year(real).set_index("year")
    for year in (1990, 2024):
        sub = real.xs(year, level="year")[["ppp", "pop"]].dropna()
        assert g.loc[year, "gini_weighted"] == pytest.approx(pairwise_gini(sub["ppp"].to_numpy(), sub["pop"].to_numpy()))
        assert g.loc[year, "n"] == len(sub)
    assert g.loc[1990, "gini_weighted"] == pytest.approx(0.609, abs=0.001)
    assert g.loc[2024, "gini_weighted"] == pytest.approx(0.455, abs=0.001)
    assert (g["pop_share_covered"] > 0.95).all()


def test_real_gini_fall_is_driven_by_china_and_india(real):
    both = gp.weighted_gini_by_year(real, exclude=["CHN", "IND"]).set_index("year")
    assert both.loc[2024, "gini_weighted"] >= both.loc[1990, "gini_weighted"]  # 0.491 -> 0.505 when written
    china = gp.weighted_gini_by_year(real, exclude=["CHN"]).set_index("year")
    assert china.loc[1990, "gini_weighted"] - china.loc[2024, "gini_weighted"] < 0.07  # the fall shrinks from 0.154 to 0.054
