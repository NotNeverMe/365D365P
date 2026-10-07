"""Unit tests for productivity.py: hand-computed examples first, then checks against the cached real data."""

import numpy as np
import pandas as pd
import pytest

import productivity as pr
from core import stats


# ------------------------------------------------------------------------------------ helpers


def wide_frame(rows: dict) -> pd.DataFrame:
    """Build a wide frame from {(iso3, year): {column: value}} like ``productivity.load()`` returns."""
    frame = pd.DataFrame.from_dict(rows, orient="index")
    frame.index = pd.MultiIndex.from_tuples(frame.index, names=["iso3", "year"])
    return frame.reindex(columns=list(pr.WB_CODES))


def sector_row(va, shares, gdp_pe=np.nan):
    out = {"gdp_pe": gdp_pe}
    out.update({f"va_{s}": v for s, v in zip(pr.SECTORS, va)})
    out.update({f"e_{s}": e for s, e in zip(pr.SECTORS, shares)})
    return out


# ------------------------------------------------------------------------------------ levels and growth


def test_relative_to_benchmark_sets_us_to_100_each_year():
    levels = pd.DataFrame({"USA": [100.0, 200.0], "FRA": [50.0, 150.0], "IND": [10.0, 40.0]}, index=[2000, 2010])
    rel = pr.relative_to_benchmark(levels)
    assert (rel["USA"] == 100).all()
    assert rel.loc[2000, "FRA"] == pytest.approx(50.0)
    assert rel.loc[2010, "FRA"] == pytest.approx(75.0)  # benchmark is the same-year US value
    assert rel.loc[2010, "IND"] == pytest.approx(20.0)


def test_relative_to_benchmark_needs_the_benchmark():
    with pytest.raises(KeyError):
        pr.relative_to_benchmark(pd.DataFrame({"FRA": [1.0]}, index=[2000]))


def test_window_cagr_hand_computed():
    levels = pd.DataFrame({"AAA": [100.0, 110.0, 121.0], "BBB": [200.0, 100.0, 50.0]}, index=[2000, 2001, 2002])
    g = pr.window_cagr(levels, 2000, 2002)
    assert g["AAA"] == pytest.approx(10.0)  # 100 -> 121 in two years is exactly 10% a year
    assert g["BBB"] == pytest.approx(-50.0)  # 200 -> 50 in two years is -50% a year
    assert g["AAA"] / 100 == pytest.approx(stats.cagr(100, 121, 2))  # agrees with core.stats.cagr


def test_window_cagr_missing_end_years_and_bad_windows():
    levels = pd.DataFrame({"AAA": [100.0, np.nan, 121.0], "BBB": [100.0, 110.0, np.nan]}, index=[2000, 2001, 2002])
    g = pr.window_cagr(levels, 2000, 2002)
    assert g["AAA"] == pytest.approx(10.0)
    assert np.isnan(g["BBB"])  # end year missing -> no growth rate, not a silent fill
    assert pr.window_cagr(levels, 1990, 2002).isna().all()  # start year not in the data
    with pytest.raises(ValueError):
        pr.window_cagr(levels, 2002, 2000)


def test_gdp_per_hour_divides_and_aligns():
    gdp = pd.DataFrame({"USA": [150_000.0, 160_000.0], "DEU": [120_000.0, 130_000.0], "CHN": [40_000.0, 50_000.0]}, index=[2022, 2023])
    hours = pd.DataFrame({"USA": [1_800.0, 1_600.0], "DEU": [1_200.0, 1_300.0]}, index=[2022, 2023])
    out = pr.gdp_per_hour(gdp, hours)
    assert list(out.columns) == ["USA", "DEU"]  # China has no hours series
    assert out.loc[2022, "USA"] == pytest.approx(150_000 / 1_800)
    assert out.loc[2023, "DEU"] == pytest.approx(100.0)
    # Same output per worker, but fewer hours: Germany ahead of the US per hour, behind per worker.
    rel_hour = pr.relative_to_benchmark(out)
    assert rel_hour.loc[2022, "DEU"] == pytest.approx(100.0 / (150_000 / 1_800) * 100)


# ------------------------------------------------------------------------------------ sector gaps


def test_sector_table_gap_measures():
    wide = wide_frame({("AAA", 2020): sector_row([10.0, 20.0, 40.0], [50.0, 20.0, 30.0])})
    t = pr.sector_table(wide, 2020).loc["AAA"]
    assert t["e_agr"] == pytest.approx(0.5)  # percentages rescaled to shares
    assert t["agg"] == pytest.approx(0.5 * 10 + 0.2 * 20 + 0.3 * 40)  # 21
    assert t["ind_to_agr"] == pytest.approx(2.0)
    assert t["srv_to_agr"] == pytest.approx(4.0)
    assert t["max_to_min"] == pytest.approx(4.0)
    nonag = (0.2 * 20 + 0.3 * 40) / 0.5  # 32
    assert t["apg"] == pytest.approx(nonag / 10)


def test_sector_table_drops_incomplete_rows_and_missing_years():
    wide = wide_frame(
        {
            ("AAA", 2020): sector_row([10.0, 20.0, 40.0], [50, 20, 30]),
            ("BBB", 2020): sector_row([10.0, np.nan, 40.0], [50, 20, 30]),  # missing industry value added
            ("CCC", 2020): sector_row([10.0, 20.0, 40.0], [100, 0, np.nan]),  # missing share
        }
    )
    assert list(pr.sector_table(wide, 2020).index) == ["AAA"]
    assert pr.sector_table(wide, 1999).empty


# ------------------------------------------------------------------------------------ shift-share

# Two sectors. Date 0: shares (0.6, 0.4), productivity (10, 30), so P0 = 6 + 12 = 18.
# Date 1: shares (0.4, 0.6), productivity (15, 36), so P1 = 6 + 21.6 = 27.6. Total change = 9.6.
#   within      = 0.6*5 + 0.4*6          = 5.4
#   between     = 10*(-0.2) + 30*(0.2)   = 4.0
#   interaction = (-0.2)*5 + (0.2)*6     = 0.2      -> 5.4 + 4.0 + 0.2 = 9.6
P0 = pd.DataFrame({"low": [10.0], "high": [30.0]}, index=["X"])
P1 = pd.DataFrame({"low": [15.0], "high": [36.0]}, index=["X"])
S0 = pd.DataFrame({"low": [0.6], "high": [0.4]}, index=["X"])
S1 = pd.DataFrame({"low": [0.4], "high": [0.6]}, index=["X"])


def test_shift_share_hand_computed_example():
    r = pr.shift_share(P0, P1, S0, S1).loc["X"]
    assert r["P0"] == pytest.approx(18.0)
    assert r["P1"] == pytest.approx(27.6)
    assert r["total"] == pytest.approx(9.6)
    assert r["within"] == pytest.approx(5.4)
    assert r["between"] == pytest.approx(4.0)
    assert r["interaction"] == pytest.approx(0.2)
    assert r["within"] + r["between"] + r["interaction"] == pytest.approx(r["total"])


def test_shift_share_no_structural_change_is_all_within():
    r = pr.shift_share(P0, P1, S0, S0).loc["X"]
    assert r["between"] == pytest.approx(0.0)
    assert r["interaction"] == pytest.approx(0.0)
    assert r["within"] == pytest.approx(r["total"])


def test_shift_share_no_productivity_change_is_all_between():
    r = pr.shift_share(P0, P0, S0, S1).loc["X"]
    assert r["within"] == pytest.approx(0.0)
    assert r["interaction"] == pytest.approx(0.0)
    assert r["between"] == pytest.approx(r["total"])
    assert r["between"] == pytest.approx(4.0)  # moving 20% of workers from 10 to 30 adds 0.2 * 20


def test_shift_share_rescales_shares_given_in_percent():
    a = pr.shift_share(P0, P1, S0, S1)
    b = pr.shift_share(P0, P1, S0 * 100, S1 * 100)
    pd.testing.assert_frame_equal(a, b)


def test_shift_share_identity_holds_for_random_inputs():
    rng = np.random.default_rng(0)
    p0, p1 = rng.uniform(1, 100, (50, 3)), rng.uniform(1, 100, (50, 3))
    s0, s1 = rng.dirichlet([1, 1, 1], 50), rng.dirichlet([1, 1, 1], 50)
    cols = ["a", "b", "c"]
    r = pr.shift_share(*(pd.DataFrame(x, columns=cols) for x in (p0, p1, s0, s1)))
    assert np.allclose(r["within"] + r["between"] + r["interaction"], r["total"])


def test_shift_share_window_converts_to_percentage_points():
    wide = wide_frame(
        {
            ("XXX", 2000): sector_row([10.0, 30.0, 30.0], [60, 40, 0]),
            ("XXX", 2010): sector_row([15.0, 36.0, 36.0], [40, 60, 0]),
            ("YYY", 2000): sector_row([5.0, 10.0, 20.0], [80, 10, 10]),  # no data in 2010: dropped
        }
    )
    out = pr.shift_share_window(wide, 2000, 2010)
    assert list(out.index) == ["XXX"]
    r = out.loc["XXX"]
    assert r["P0"] == pytest.approx(18.0)
    assert r["growth_pct"] == pytest.approx(9.6 / 18.0 * 100)
    assert r["within_pp"] == pytest.approx(5.4 / 18.0 * 100)
    assert r["between_pp"] == pytest.approx(4.0 / 18.0 * 100)
    assert r["interaction_pp"] == pytest.approx(0.2 / 18.0 * 100)
    assert r["within_pp"] + r["between_pp"] + r["interaction_pp"] == pytest.approx(r["growth_pct"])
    with pytest.raises(ValueError):
        pr.shift_share_window(wide, 2010, 2000)


def test_summarise_by_median_and_count():
    t = pd.DataFrame({"region": ["A", "A", "A", "B"], "within_pp": [1.0, 2.0, 9.0, 4.0]})
    out = pr.summarise_by(t, "region", ["within_pp"])
    assert out.loc["A", "within_pp"] == 2.0  # median, not mean
    assert out.loc["A", "economies"] == 3
    assert out.index[0] == "B"  # sorted by the first value column, largest first


# ------------------------------------------------------------------------------------ real cached data


@pytest.fixture(scope="module")
def wide():
    return pr.load()


def test_real_coverage_floors(wide):
    cov = pr.coverage(wide, total_economies=217)
    assert cov.loc["gdp_pe", "economies_ever"] >= 170
    assert cov.loc["va_agr", "economies_ever"] >= 170
    assert cov.loc["e_agr", "first_year"] == 1991
    assert cov.loc["gdp_pe", "last_year"] >= 2023


def test_real_us_level_checked_by_hand(wide):
    # World Bank: US GDP per person employed 2023 = 150,827.9 (constant 2021 PPP $).
    pe = pr.level_matrix(wide, "gdp_pe")
    assert pe.loc[2023, "USA"] == pytest.approx(150_827.9, abs=0.5)
    assert pr.relative_to_benchmark(pe).loc[2023, "USA"] == 100.0


def test_real_us_has_no_sector_series_beyond_2015(wide):
    # A documented gap: the World Bank publishes US sector value added per worker for 2015 only.
    usa = wide.xs("USA", level="iso3")[["va_agr", "va_ind", "va_srv"]].dropna(how="all")
    assert list(usa.index) == [2015]
    assert "USA" not in pr.sector_table(wide, 2019).index


def test_real_shift_share_identity_and_china_value(wide):
    ss = pr.shift_share_window(wide, 2000, 2019)
    assert len(ss) >= 140
    gap = (ss[["within_pp", "between_pp", "interaction_pp"]].sum(axis=1) - ss["growth_pct"]).abs().max()
    assert gap < 1e-8
    # Verified by running the module: China's sector-built productivity grew 368% between 2000 and 2019.
    assert ss.loc["CHN", "growth_pct"] == pytest.approx(368.2, abs=0.1)
    assert ss.loc["CHN", "within_pp"] > ss.loc["CHN", "between_pp"] > 0


def test_real_sector_gap_agriculture_is_usually_lowest(wide):
    t = pr.sector_table(wide, 2019)
    lowest_is_agr = (t[["va_agr", "va_ind", "va_srv"]].idxmin(axis=1) == "va_agr").mean()
    assert len(t) >= 150
    assert lowest_is_agr > 0.8
    assert (t["apg"] > 1).mean() > 0.85


def test_real_hours_and_per_hour_estimate(wide):
    hours = pr.load_hours()
    assert hours.shape[1] >= 55
    assert hours.loc[2023, "USA"] == pytest.approx(1788.9, abs=0.1)  # Penn World Table value on FRED
    pe = pr.level_matrix(wide, "gdp_pe")
    per_hour = pr.gdp_per_hour(pe, hours)
    assert per_hour.loc[2023, "USA"] == pytest.approx(150_827.9 / 1788.9, rel=1e-4)
    rel = pr.relative_to_benchmark(per_hour)
    assert rel.loc[2023, "DEU"] > pr.relative_to_benchmark(pe).loc[2023, "DEU"]  # fewer hours -> better per hour than per worker


def test_real_us_output_per_hour_series():
    s = pr.load_us_output_per_hour()
    assert s.index.min() == 1947
    assert s.loc[2017] == pytest.approx(100.0, abs=0.5)  # index base year 2017 = 100 (annual mean of quarters)
    assert s.loc[2023] > s.loc[2013]
