"""Unit tests for inflation_wages.py: hand-computed examples first, then checks against the cached real data."""

import numpy as np
import pandas as pd
import pytest

import inflation_wages as iw


def monthly(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


def frame(wage, cpi, start="2020-01-01"):
    return pd.DataFrame({"wage": monthly(wage, start), "cpi": monthly(cpi, start)})


# ------------------------------------------------------------------------------------ growth on a calendar grid


def test_growth_12m_is_date_based_across_a_missing_month():
    s = monthly([100.0 * 1.01**m for m in range(30)])  # 1% a month: every 12-month change is 1.01**12 - 1
    holey = s.drop(pd.Timestamp("2021-06-01"))
    g = iw.growth(holey, "12m")
    expected = (1.01**12 - 1) * 100
    assert g.loc["2021-07-01"] == pytest.approx(expected)  # compared with July 2020, not with a row 12 places back
    assert g.loc["2021-12-01"] == pytest.approx(expected)
    assert np.isnan(g.loc["2021-06-01"])  # the hole itself has no growth rate
    assert np.isnan(g.loc["2020-06-01"])  # nothing a year earlier


def test_growth_kinds_and_quarterly_scaling():
    s = monthly([100.0, 101.0, 102.01, 103.0301, 104.060401])
    assert iw.growth(s, "1m").iloc[1] == pytest.approx(1.0)
    assert iw.growth(s, "3m").iloc[3] == pytest.approx((1.01**3 - 1) * 100)
    d = iw.growth(monthly(list(100 * 1.01 ** np.arange(26))), "12m_diff")
    assert d.dropna().abs().max() < 1e-9  # constant 12-month rate -> zero change
    q = pd.Series([100.0, 110.0, 121.0, 133.1, 146.41], index=pd.date_range("2020-01-01", periods=5, freq="QS"))
    assert iw.growth(q, "12m", ppy=4).iloc[4] == pytest.approx(46.41)  # four quarters back
    assert iw.growth(q, "3m", ppy=4).iloc[1] == pytest.approx(10.0)  # one quarter
    with pytest.raises(ValueError):
        iw.growth(s, "weekly")


def test_periods_per_year():
    assert iw.periods_per_year(monthly([1, 2, 3, 4]).index) == 12
    assert iw.periods_per_year(pd.date_range("2020-01-01", periods=5, freq="QS")) == 4


# ------------------------------------------------------------------------------------ alignment and real wages


def test_aligned_monthly_keeps_common_dates_only():
    wage = monthly([10.0, 11.0, 12.0])
    cpi = monthly([100.0, 101.0], start="2019-12-01")  # Dec, Jan
    out = iw.aligned(wage, cpi)
    assert list(out.index) == [pd.Timestamp("2020-01-01")]
    assert out.loc["2020-01-01", "cpi"] == 101.0


def test_aligned_quarterly_wage_uses_quarter_average_cpi_and_drops_partial_quarters():
    wage = pd.Series([300.0, 330.0, 360.0], index=pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01"]))
    cpi = monthly([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0])  # Jan..Aug: Q3 has only Jul and Aug
    out = iw.aligned(wage, cpi)
    assert list(out.index) == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-04-01")]
    assert out.loc["2020-01-01", "cpi"] == pytest.approx(101.0)  # mean of 100, 101, 102
    assert out.loc["2020-04-01", "cpi"] == pytest.approx(104.0)


def test_real_wage_and_cumulative_change_by_hand():
    df = frame([20.0, 22.0, 23.1], [200.0, 205.0, 220.0])
    real = iw.real_wage(df)
    assert real.iloc[0] == pytest.approx(10.0)  # 20 / 200 * 100
    assert real.iloc[1] == pytest.approx(22 / 205 * 100)
    c = iw.cumulative_real_change(real, "2020-01-01")
    assert c.iloc[0] == 0.0
    assert c.iloc[2] == pytest.approx((23.1 / 220) / (20 / 200) * 100 - 100)  # +5.0%
    assert iw.cumulative_real_change(real, "2020-01-15").index[0] == pd.Timestamp("2020-02-01")  # first obs on/after base
    with pytest.raises(ValueError):
        iw.cumulative_real_change(real, "2021-01-01")


def test_real_growth_formula_and_negative_share():
    wage = [100.0 * 1.05 ** (m / 12) for m in range(25)]
    cpi = [100.0 * 1.03 ** (m / 12) for m in range(25)]
    r = iw.real_growth(frame(wage, cpi), "12m").dropna()
    assert r.iloc[-1] == pytest.approx((1.05 / 1.03 - 1) * 100)  # 1.9417%
    assert iw.negative_share(r) == 0.0
    assert iw.negative_share(pd.Series([-1.0, 1.0, np.nan, 2.0])) == pytest.approx(1 / 3)
    assert np.isnan(iw.negative_share(pd.Series([np.nan])))


# ------------------------------------------------------------------------------------ episodes, annual, decades

# 48 months. CPI jumps from 100 to 110 in month 12 (and wages from 100 to 104), so for months 12-23 the
# 12-month inflation is 10% against 4% wage growth: a 6 pp gap for exactly 12 months. Months 24-35: flat,
# no gap. Months 36-38: CPI spikes to 121 (10% above its level a year earlier) while wages stand still: a
# 10 pp gap that lasts only 3 months.
CPI_PATH = [100.0] * 12 + [110.0] * 24 + [121.0] * 3 + [110.0] * 9
WAGE_PATH = [100.0] * 12 + [104.0] * 36


def test_gap_episodes_hand_computed():
    df = frame(WAGE_PATH, CPI_PATH)
    ep = iw.gap_episodes(df, min_periods=6)
    assert len(ep) == 1  # the 3-month spike is below min_periods
    e = ep.iloc[0]
    assert e["start"] == pd.Timestamp("2021-01-01")
    assert e["end"] == pd.Timestamp("2021-12-01")
    assert e["periods"] == 12
    assert e["mean_gap_pp"] == pytest.approx(6.0)
    assert e["peak_gap_pp"] == pytest.approx(6.0)
    assert e["inflation_at_peak"] == pytest.approx(10.0)
    assert e["wage_growth_at_peak"] == pytest.approx(4.0)
    short = iw.gap_episodes(df, min_periods=3)
    assert len(short) == 2
    assert short.iloc[1]["peak_gap_pp"] == pytest.approx(10.0)
    assert short.iloc[1]["periods"] == 3


def test_gap_episode_does_not_jump_across_a_missing_month():
    df = frame(WAGE_PATH, CPI_PATH).drop(pd.Timestamp("2021-06-01"))
    ep = iw.gap_episodes(df, min_periods=3)
    first_two = ep[ep["start"] < pd.Timestamp("2022-01-01")]
    assert len(first_two) == 2  # 2021-01..05 and 2021-07..12, not one run with a hidden hole
    assert list(first_two["periods"]) == [5, 6]


def test_annual_table_by_hand_and_partial_year_excluded():
    wage = [100.0] * 12 + [110.0] * 12 + [99.0] * 6
    cpi = [100.0] * 12 + [105.0] * 12 + [120.0] * 6
    t = iw.annual_table(frame(wage, cpi))
    assert list(t.index) == [2021]  # 2020 has no previous year, 2022 is incomplete
    r = t.loc[2021]
    assert r["wage_growth_pct"] == pytest.approx(10.0)
    assert r["inflation_pct"] == pytest.approx(5.0)
    assert r["real_growth_pct"] == pytest.approx((1.10 / 1.05 - 1) * 100)
    assert r["gap_pp"] == pytest.approx(-5.0)


def test_decade_summary_compound_rates_by_hand():
    months = 12 * 10 + 2  # Dec 1969 .. Jan 1980
    cpi = [100.0 * 1.005**m for m in range(months)]
    wage = [100.0 * 1.004**m for m in range(months)]
    d = iw.decade_summary(frame(wage, cpi, start="1969-12-01"))
    assert list(d["decade"]) == ["1970s"]  # 1969 and Jan 1980 are less than a year of change
    r = d.iloc[0]
    assert r["from"] == pd.Timestamp("1969-12-01") and r["to"] == pd.Timestamp("1979-12-01")
    assert r["inflation_pct"] == pytest.approx((1.005**12 - 1) * 100, abs=0.01)  # 6.17% a year
    assert r["wage_growth_pct"] == pytest.approx((1.004**12 - 1) * 100, abs=0.01)
    assert r["real_wage_growth_pct"] == pytest.approx(((1.004 / 1.005) ** 12 - 1) * 100, abs=0.01)  # -1.19%
    assert r["share_falling_real_wage"] == 1.0  # wages lag prices every single month


# ------------------------------------------------------------------------------------ lead / lag


def _persistent(n, seed=0):
    rng = np.random.default_rng(seed)
    e = rng.normal(size=n)
    x = np.zeros(n)
    for t in range(1, n):
        x[t] = 0.8 * x[t - 1] + e[t]
    return pd.Series(x, index=pd.date_range("1990-01-01", periods=n, freq="MS"))


def test_cross_correlation_finds_a_known_lag_and_sign():
    infl = _persistent(400)
    wage_follows = infl.shift(3).fillna(0.0) + np.random.default_rng(1).normal(scale=0.05, size=400)
    cc = iw.cross_correlation(infl, wage_follows, max_lag=12)
    pk = iw.peak_lag(cc)
    assert pk["lag"] == 3  # wage growth at t+3 matches inflation at t: wages follow
    assert pk["correlation"] > 0.95
    cc2 = iw.cross_correlation(wage_follows, infl, max_lag=12)  # swap roles: now inflation follows
    assert iw.peak_lag(cc2)["lag"] == -3
    assert list(cc.index) == list(range(-12, 13))


def test_cross_correlation_lag0_equals_pearson_and_input_checks():
    a, b = _persistent(200, 1), _persistent(200, 2)
    cc = iw.cross_correlation(a, b, max_lag=6)
    assert cc[0] == pytest.approx(np.corrcoef(a, b)[0, 1])
    with pytest.raises(ValueError):
        iw.cross_correlation(a.iloc[:30], b.iloc[:30], max_lag=24)


def test_cross_correlation_uses_the_longest_unbroken_stretch():
    a = _persistent(300, 3)
    b = a.shift(2).fillna(0.0)
    holey_b = b.copy()
    holey_b.iloc[250] = np.nan  # a hole near the end: the first 250 months are the longest stretch
    z = iw.longest_unbroken(pd.concat({"i": a, "w": holey_b}, axis=1))
    assert len(z) == 250 and z.index[0] == a.index[0]
    pk = iw.peak_lag(iw.cross_correlation(a, holey_b, max_lag=10))
    assert pk["lag"] == 2


def test_peak_lag_plateau():
    cc = pd.Series([0.1, 0.5, 0.78, 0.8, 0.79, 0.3], index=pd.RangeIndex(-2, 4, name="lag"))
    pk = iw.peak_lag(cc, tolerance=0.02)
    assert pk["lag"] == 1 and pk["correlation"] == 0.8 and pk["lag0"] == 0.78
    assert pk["plateau"] == (0, 2)


# ------------------------------------------------------------------------------------ cross-country panel


def test_annual_means_complete_years_only_and_contiguous():
    s = monthly(list(range(1, 31)), start="2019-01-01")  # Jan 2019 .. Jun 2021
    a = iw.annual_means(s)
    assert list(a.index) == [2019, 2020, 2021]
    assert a[2019] == pytest.approx(6.5)  # mean of 1..12
    assert a[2020] == pytest.approx(18.5)
    assert np.isnan(a[2021])  # six months only
    q = pd.Series(range(1, 7), index=pd.date_range("2019-01-01", periods=6, freq="QS"), dtype=float)
    aq = iw.annual_means(q)
    assert aq[2019] == pytest.approx(2.5) and np.isnan(aq[2020])


@pytest.fixture
def small_panel(monkeypatch):
    monkeypatch.setattr(iw, "PANEL_WAGE_IDS", {"AAA": "x", "BBB": "y", "CCC": None, "DDD": "z"})
    idx = lambda start, n: pd.date_range(start, periods=n, freq="MS")  # noqa: E731
    wages = {
        "AAA": pd.Series(np.repeat([100.0, 105.0, 110.25], 12), index=idx("2019-01-01", 36)),  # +5% a year, 2019-2021
        "BBB": pd.Series(np.repeat([100.0, 105.0], 12), index=idx("2019-01-01", 24)),  # ends in 2020
        "DDD": pd.Series(np.repeat([100.0, 100.0, 100.0], 12), index=idx("2019-01-01", 36)),
    }
    infl = pd.DataFrame({"AAA": [np.nan, 3.0, 2.0], "BBB": [np.nan, 3.0, 2.0], "DDD": [np.nan, np.nan, 2.0]}, index=[2019, 2020, 2021])
    return wages, infl


def test_panel_status_drops_with_reasons(small_panel):
    wages, infl = small_panel
    st = iw.panel_status(wages, infl, base_year=2019, last_year=2021)
    assert st["included"].to_dict() == {"AAA": True, "BBB": False, "CCC": False, "DDD": False}
    assert "no complete year 2021" in st.loc["BBB", "reason"] and "2020-12" in st.loc["BBB", "reason"]
    assert "no OECD" in st.loc["CCC", "reason"]
    assert "2020" in st.loc["DDD", "reason"] and "CPI inflation" in st.loc["DDD", "reason"]
    assert iw.panel_status(wages, infl, base_year=2019, last_year=2020)["included"]["BBB"]  # recent enough for a shorter window


def test_panel_real_wages_by_hand(small_panel):
    wages, infl = small_panel
    st = iw.panel_status(wages, infl, 2019, 2021)
    p = iw.panel_real_wages(wages, infl, st, 2019, 2021)
    assert list(p["iso3"].unique()) == ["AAA"] and list(p["year"]) == [2020, 2021]
    assert p["wage_growth_pct"].tolist() == pytest.approx([5.0, 5.0])
    assert p["real_growth_pct"].tolist() == pytest.approx([(1.05 / 1.03 - 1) * 100, (1.05 / 1.02 - 1) * 100])  # 1.9417, 2.9412
    assert p["cumulative_real_pct"].iloc[-1] == pytest.approx((1.05 / 1.03 * 1.05 / 1.02 - 1) * 100)  # 4.9418
    s = iw.panel_summary(p).loc["AAA"]
    assert s["years"] == 2 and s["years_falling"] == 0
    assert s["worst_year"] == 2020  # the smaller real gain


# ------------------------------------------------------------------------------------ real cached data


@pytest.fixture(scope="module")
def us():
    return iw.load_us()


def test_real_series_coverage_and_known_hole(us):
    cpi = us["cpi"].dropna()
    assert cpi.index.min() == pd.Timestamp("1947-01-01") and cpi.index.max() >= pd.Timestamp("2025-12-01")
    assert us["AHETPI"].dropna().index.min() == pd.Timestamp("1964-01-01")
    assert us["CES0500000003"].dropna().index.min() == pd.Timestamp("2006-03-01")
    assert us["LEU0252881500Q"].dropna().index.min() == pd.Timestamp("1979-01-01")
    assert pd.Timestamp("2025-10-01") not in cpi.index  # BLS published no October 2025 CPI (federal shutdown)


def test_real_wage_checked_by_hand(us):
    # AHETPI: $2.50 in Jan 1964 and $32.53 in Aug 2026. CPI-U: 30.94 and 334.131.
    # Real wage ratio = (32.53 / 334.131) / (2.50 / 30.94) = 1.2049.
    df = iw.aligned(us["AHETPI"], us["cpi"].dropna())
    assert df.loc["1964-01-01", "wage"] == 2.5 and df.loc["1964-01-01", "cpi"] == 30.94
    c = iw.cumulative_real_change(iw.real_wage(df), "1964-01-01")
    assert c.loc["2026-08-01"] == pytest.approx(20.49, abs=0.01)


def test_real_yoy_inflation_uses_calendar_dates_across_the_2025_hole(us):
    cpi = us["cpi"].dropna()
    g = iw.growth(cpi, "12m")
    assert g.loc["2026-01-01"] == pytest.approx((cpi["2026-01-01"] / cpi["2025-01-01"] - 1) * 100)  # 2.39%
    assert np.isnan(g.loc["2025-10-01"])


def test_real_deflation_agrees_with_bls_real_series(us):
    from core import fred

    med = iw.aligned(us["LEU0252881500Q"], us["cpi"].dropna())
    bls = fred.series(iw.BLS_REAL_MEDIAN)
    both = pd.concat([iw.real_wage(med), bls], axis=1, keys=["mine", "bls"], sort=True).dropna()
    gap = (both["mine"] / both["bls"] - 1).abs()
    assert len(both) > 150
    assert gap.mean() < 0.01  # BLS rounds to whole dollars; mean absolute gap is 0.6%
    assert gap.max() < 0.02


def test_real_decades_and_episodes(us):
    df = iw.aligned(us["AHETPI"], us["cpi"].dropna())
    d = iw.decade_summary(df).set_index("decade")
    assert d.loc["1970s", "inflation_pct"] == pytest.approx(7.39, abs=0.01)
    assert d.loc["1980s", "real_wage_growth_pct"] < 0 < d.loc["2010s", "real_wage_growth_pct"]
    ep = iw.gap_episodes(df, 6)
    assert len(ep) == 10
    assert ep["peak_gap_pp"].max() == pytest.approx(7.04, abs=0.01)  # March 1980
    assert ep.loc[ep["peak_gap_pp"].idxmax(), "peak_date"] == pd.Timestamp("1980-03-01")
    assert (ep["peak_gap_pp"] > 0).all() and (ep["periods"] >= 6).all()


def test_real_cross_correlation_is_a_short_positive_lag_on_12_month_rates(us):
    df = iw.aligned(us["AHETPI"], us["cpi"].dropna())
    infl, wage = iw.growth(df["cpi"], "12m"), iw.growth(df["wage"], "12m")
    pk = iw.peak_lag(iw.cross_correlation(infl.loc["1983":"2019"], wage.loc["1983":"2019"], 36))
    assert 0 <= pk["lag"] <= 6
    assert 0.3 < pk["correlation"] < 0.5


def test_real_panel_inclusion_and_a_hand_checked_country(us):
    from core import worldbank as wb

    wages, infl = iw.load_panel_wages(), iw.panel_inflation(us["cpi"].dropna())
    st = iw.panel_status(wages, infl, 2019, 2025)
    assert int(st["included"].sum()) >= 20
    assert "2025" in st.loc["USA", "reason"]  # no complete 2025 CPI average because October 2025 is missing
    assert "no OECD" in st.loc["CHE", "reason"]
    assert not st.loc["TUR", "included"]
    p = iw.panel_real_wages(wages, infl, st, 2019, 2025)
    # Germany by hand: product of (1 + wage growth) / (1 + inflation) over 2020-2025, from the raw inputs.
    annual = iw.annual_means(wages["DEU"])
    factor = 1.0
    for y in range(2020, 2026):
        factor *= (annual[y] / annual[y - 1]) / (1 + wb.indicator(iw.WB_INFLATION).query("iso3 == 'DEU' and year == @y")["value"].iloc[0] / 100)
    deu = p[p["iso3"] == "DEU"]["cumulative_real_pct"].iloc[-1]
    assert deu == pytest.approx((factor - 1) * 100)
    assert deu < 0  # real manufacturing earnings in Germany were below their 2019 level in 2025


def test_real_oecd_cpi_series_are_stale_which_is_why_the_panel_uses_world_bank_prices():
    last = iw.oecd_cpi_last_dates()
    assert len(last) >= 28
    assert last["cpi_series"].str.startswith("CPALTT01").all()
    # If this fails the OECD CPI series have been refreshed and the panel could use them directly.
    assert last["last_date"].max() < pd.Timestamp("2026-01-01")
    assert last.loc["JPN", "last_date"] < pd.Timestamp("2022-01-01")
