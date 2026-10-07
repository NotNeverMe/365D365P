"""Unit tests for growth_heatmap.py: hand-computed examples first, then checks against the cached real data."""

import numpy as np
import pandas as pd
import pytest

import growth_heatmap as gh
from core import stats


def levels(**cols):
    """Levels frame, rows = year. ``levels(AAA=[100, 121], index=[2000, 2002])`` style via the ``index`` key."""
    index = cols.pop("index")
    return pd.DataFrame(cols, index=index)


META = pd.DataFrame(
    {
        "iso3": ["AAA", "BBB", "CCC"],
        "name": ["Alpha", "Beta", "Gamma"],
        "region": ["North", "North", "South"],
        "income_group": ["High income", "High income", "Low income"],
    }
)


# ------------------------------------------------------------------------------------ growth


def test_window_cagr_hand_computed():
    lv = levels(AAA=[100.0, 121.0], BBB=[200.0, 50.0], index=[2000, 2002])
    g = gh.window_cagr(lv, 2000, 2002)
    assert g["AAA"] == pytest.approx(10.0)  # 100 -> 121 over two years: exactly 10% a year
    assert g["BBB"] == pytest.approx(-50.0)  # 200 -> 50 over two years: 0.5 each year
    assert g["AAA"] / 100 == pytest.approx(stats.cagr(100, 121, 2))


def test_window_cagr_ten_year_doubling():
    lv = levels(AAA=[1.0, 2.0], index=[1960, 1970])
    assert gh.window_cagr(lv, 1960, 1970)["AAA"] == pytest.approx((2 ** 0.1 - 1) * 100)  # 7.177%


def test_window_cagr_missing_and_invalid_inputs():
    lv = levels(AAA=[100.0, np.nan, 121.0], BBB=[np.nan, 5.0, 6.0], CCC=[0.0, 1.0, 2.0], index=[2000, 2001, 2002])
    g = gh.window_cagr(lv, 2000, 2002)
    assert g["AAA"] == pytest.approx(10.0)  # a gap in the middle does not matter
    assert np.isnan(g["BBB"])  # start missing
    assert np.isnan(g["CCC"])  # a zero start level has no growth rate
    assert gh.window_cagr(lv, 1990, 2002).isna().all()  # year not in the data
    with pytest.raises(ValueError):
        gh.window_cagr(lv, 2002, 2002)


def test_average_of_annual_rates_overstates_growth_when_volatile():
    # +50% then -50%: the level ends 25% lower, yet the average annual rate is exactly zero.
    lv = levels(AAA=[100.0, 150.0, 75.0], index=[2000, 2001, 2002])
    annual = lv.pct_change() * 100
    mean = gh.mean_annual_growth(annual, 2000, 2002)["AAA"]
    cagr = gh.window_cagr(lv, 2000, 2002)["AAA"]
    assert mean == pytest.approx(0.0)
    assert cagr == pytest.approx((np.sqrt(0.75) - 1) * 100)  # -13.397%
    both = gh.cagr_vs_mean_annual(lv, annual, 2000, 2002)
    assert both.loc["AAA", "mean_minus_cagr_pp"] == pytest.approx(13.397, abs=1e-3)


def test_mean_annual_growth_needs_every_year():
    annual = pd.DataFrame({"AAA": [np.nan, 2.0, 4.0, 6.0], "BBB": [np.nan, 1.0, np.nan, 3.0]}, index=[2000, 2001, 2002, 2003])
    m = gh.mean_annual_growth(annual, 2000, 2003)
    assert m["AAA"] == pytest.approx(4.0)
    assert np.isnan(m["BBB"])


def test_make_windows():
    assert gh.make_windows(1960, 2020, 10) == [(1960, 1970), (1970, 1980), (1980, 1990), (1990, 2000), (2000, 2010), (2010, 2020)]
    assert gh.make_windows(1960, 2025, 10, include_partial=True)[-1] == (2020, 2025)
    assert gh.make_windows(1960, 2025, 10)[-1] == (2010, 2020)
    assert len(gh.make_windows(1960, 2025, 5)) == 13
    assert gh.make_windows(1960, 2020, 10, include_partial=True)[-1] == (2010, 2020)  # exact fit: no extra window
    with pytest.raises(ValueError):
        gh.make_windows(1960, 2020, 0)
    assert gh.window_label((1960, 1970)) == "1960-1970"


# ------------------------------------------------------------------------------------ tables


def test_window_table_keeps_economies_without_data():
    lv = levels(AAA=[100.0, 121.0], BBB=[50.0, np.nan], index=[2000, 2002])  # CCC has no column at all
    t = gh.window_table(lv, 2000, 2002, META)
    assert list(t["iso3"]) == ["AAA", "BBB", "CCC"]  # nobody dropped: the map needs the grey ones
    assert t.set_index("iso3").loc["AAA", "cagr_pct"] == pytest.approx(10.0)
    assert t["cagr_pct"].isna().tolist() == [False, True, True]
    assert t.set_index("iso3").loc["AAA", "end_level"] == 121.0


def test_panel_is_long_with_every_economy_in_every_window():
    lv = levels(AAA=[100.0, 110.0, 133.1], BBB=[10.0, 10.0, 12.1], index=[2000, 2001, 2002])
    p = gh.panel(lv, [(2000, 2001), (2000, 2002)], META)
    assert len(p) == 2 * len(META)
    assert set(p["window"]) == {"2000-2001", "2000-2002"}
    row = p[(p["window"] == "2000-2002") & (p["iso3"] == "AAA")].iloc[0]
    assert row["cagr_pct"] == pytest.approx(15.37, abs=0.01)  # sqrt(1.331) - 1


def test_coverage_and_negative_share():
    g = pd.Series({"A": -1.0, "B": 2.0, "C": np.nan, "D": 3.0})
    assert gh.coverage(g, 4) == {"with_data": 3, "total": 4, "share": 0.75}
    assert gh.negative_share(g) == pytest.approx(1 / 3)  # NaN is not counted as growth or decline
    assert np.isnan(gh.negative_share(pd.Series([np.nan])))


def test_window_summary_hand_computed():
    lv = levels(AAA=[100.0, 90.0], BBB=[100.0, 121.0], CCC=[100.0, 110.0], DDD=[np.nan, 5.0], index=[2000, 2002])
    s = gh.window_summary(lv, [(2000, 2002)], total_economies=5).iloc[0]
    assert s["with_data"] == 3
    assert s["coverage"] == pytest.approx(0.6)
    assert s["negative_share"] == pytest.approx(1 / 3)
    assert s["median_cagr_pct"] == pytest.approx((np.sqrt(1.1) - 1) * 100)


def test_top_bottom_orders_and_ignores_missing():
    t = pd.DataFrame({"iso3": list("ABCDE"), "cagr_pct": [1.0, 5.0, np.nan, -2.0, 3.0]})
    top, bottom = gh.top_bottom(t, 2)
    assert list(top["iso3"]) == ["B", "E"]
    assert list(bottom["iso3"]) == ["D", "A"]  # slowest first
    top, bottom = gh.top_bottom(t, 10)
    assert len(top) == len(bottom) == 4  # fewer economies with data than n


def test_region_summary_quartiles_by_hand():
    t = pd.DataFrame({"region": ["A"] * 5 + ["B"] * 3, "cagr_pct": [1.0, 2.0, 3.0, 4.0, 5.0, 10.0, np.nan, 20.0]})
    r = gh.region_summary(t)
    a = r.loc["A"]
    assert (a["median"], a["q1"], a["q3"], a["iqr"]) == (3.0, 2.0, 4.0, 2.0)
    b = r.loc["B"]
    assert (b["economies"], b["with_data"]) == (3, 2)
    assert b["median"] == pytest.approx(15.0)
    assert r.index[0] == "B"  # sorted by median, highest first


def test_color_limit_is_symmetric_rounded_up_and_floored():
    assert gh.color_limit([-3.2, 1.0, 2.0], quantile=1.0) == 4.0  # rounds up the largest |value|
    assert gh.color_limit([1, 2, 3, 4, 5], quantile=1.0) == 5.0
    assert gh.color_limit([0.2, -0.1]) == 1.0  # floor
    assert gh.color_limit([np.nan]) == 1.0
    assert gh.color_limit([100.0] + [1.0] * 99, quantile=0.9) == 1.0  # one outlier cannot stretch the scale


# ------------------------------------------------------------------------------------ real cached data


@pytest.fixture(scope="module")
def wide():
    return gh.load()


@pytest.fixture(scope="module")
def pc(wide):
    return gh.level_matrix(wide, "per_capita")


def test_real_economies_list_excludes_aggregates():
    meta = gh.economies()
    assert len(meta) == 217
    assert not {"WLD", "EUU", "LIC"} & set(meta["iso3"])
    assert meta["region"].nunique() == 7


def test_real_coverage_grows_over_time(pc):
    n = {y: int(pc.loc[y].notna().sum()) for y in (1960, 1990, 2010)}
    assert n[1960] == 107  # verified by running the module
    assert n[1960] < n[1990] < n[2010]
    assert pc.index.max() >= 2024


def test_real_cagr_checked_by_hand(pc):
    # US GDP per capita: 39,200.07 (1990) -> 61,047.96 (2019): (61047.96 / 39200.07) ** (1/29) - 1 = 1.54% a year.
    g = gh.window_cagr(pc, 1990, 2019)
    assert g["USA"] == pytest.approx(1.539, abs=0.001)
    # China: 917.19 -> 10,356.29: ratio 11.29, 29 years, 8.72% a year.
    assert g["CHN"] == pytest.approx(8.718, abs=0.001)


def test_real_annual_growth_series_is_consistent_with_levels(wide, pc):
    zg = gh.level_matrix(wide, "annual_pc_growth")
    diff = (pc.pct_change(fill_method=None) * 100 - zg).abs().stack()
    assert len(diff) > 10_000
    assert diff.max() < 1e-3


def test_real_mean_of_annual_growth_is_never_below_cagr(wide, pc):
    zg = gh.level_matrix(wide, "annual_pc_growth")
    cmp_ = gh.cagr_vs_mean_annual(pc, zg, 1990, 2019)
    assert len(cmp_) > 150
    assert (cmp_["mean_minus_cagr_pp"] > -1e-6).all()  # arithmetic mean >= geometric mean
    assert cmp_["mean_minus_cagr_pp"].max() > 1.0  # and for some countries the gap is large


def test_real_window_table_and_region_summary(pc):
    t = gh.window_table(pc, 1990, 2019)
    assert len(t) == 217
    assert 150 < t["cagr_pct"].notna().sum() < 217  # some economies lack data: they stay in the table
    r = gh.region_summary(t)
    assert r["economies"].sum() == 217
    assert r["with_data"].sum() == t["cagr_pct"].notna().sum()
    assert (r["q1"] <= r["median"]).all() and (r["median"] <= r["q3"]).all()
    top, bottom = gh.top_bottom(t)
    assert top["cagr_pct"].is_monotonic_decreasing and bottom["cagr_pct"].is_monotonic_increasing
    assert top.loc[0, "cagr_pct"] > 8  # Equatorial Guinea / China territory
    assert bottom.loc[0, "cagr_pct"] < 0
