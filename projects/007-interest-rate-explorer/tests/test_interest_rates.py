"""Unit tests (small frames with hand-computed answers) plus sanity checks on the cached real data."""

import numpy as np
import pandas as pd
import pytest

import interest_rates as ir
from core import fred


def monthly(values, start="2020-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


# ------------------------------------------------------------------ calculations


def test_yoy_uses_calendar_months_not_positions():
    # 2020 at 100 except June missing; 2021 at 110. Every 2021 month has a 2020 partner except June.
    level = monthly([100.0] * 24)
    level.iloc[12:] = 110.0
    level = level.drop(pd.Timestamp("2020-06-01"))
    out = ir.yoy(level)
    assert len(out) == 11
    assert pd.Timestamp("2021-06-01") not in out.index
    assert out.round(6).eq(10.0).all()


def test_yoy_quarterly():
    q = pd.Series([100.0, 100.0, 100.0, 100.0, 103.0], index=pd.date_range("2020-01-01", periods=5, freq="QS"))
    out = ir.yoy(q, periods=4, freq="QS")
    assert list(out.round(6)) == [3.0]


def test_real_rate_is_nominal_minus_inflation_on_common_months():
    nominal = monthly([5.0, 5.0, 5.0])
    infl = monthly([2.0, 7.0], start="2020-02-01")
    out = ir.real_rate(nominal, infl)
    assert list(out.index) == list(pd.date_range("2020-02-01", periods=2, freq="MS"))
    assert list(out) == [3.0, -2.0]


def test_negative_spells_counts_runs_and_splits_on_missing_month():
    # Jan..Aug 2020; July is missing, so the negative May-Jun run must not join the negative August.
    real = monthly([1.0, -1.0, -2.0, 3.0, -0.5, -0.5, -1.0, -1.0]).drop(pd.Timestamp("2020-07-01"))
    spells = ir.negative_spells(real)
    assert list(spells["months"]) == [2, 2, 1]
    assert spells.loc[0, "lowest_real"] == -2.0
    assert spells.loc[0, "lowest_date"] == pd.Timestamp("2020-03-01")
    assert spells.loc[1, "mean_real"] == pytest.approx(-0.5)
    assert spells["months"].sum() == int((real < 0).sum())


def test_negative_spells_empty_when_never_negative():
    assert ir.negative_spells(monthly([1.0, 2.0])).empty


def test_swing_points_zigzag_by_hand():
    rate = monthly([1.0, 2.0, 3.0, 2.8, 1.4, 1.0, 2.0, 3.0])
    pts = ir.swing_points(rate, threshold=1.5)
    assert list(pts["kind"]) == ["trough", "peak", "trough", "peak"]
    assert list(pts["rate"]) == [1.0, 3.0, 1.0, 3.0]
    assert list(pts["date"]) == [rate.index[i] for i in (0, 2, 5, 7)]
    assert list(pts["confirmed"]) == [True, True, True, False]


def test_swing_points_ignore_moves_smaller_than_threshold():
    assert ir.swing_points(monthly([1.0, 1.4, 1.0, 1.4]), threshold=1.5).empty


def test_hiking_cycles_table():
    rate = monthly([1.0, 2.0, 3.0, 2.8, 1.4, 1.0, 2.0, 3.0])
    cycles = ir.hiking_cycles(rate, threshold=1.5)
    assert len(cycles) == 2
    first, second = cycles.iloc[0], cycles.iloc[1]
    assert (first["trough_rate"], first["peak_rate"], first["rise_pp"]) == (1.0, 3.0, 2.0)
    assert first["liftoff_date"] == rate.index[1]  # first month >= trough + 0.25
    assert first["months_liftoff_to_peak"] == 1
    assert first["next_trough_rate"] == 1.0 and first["cut_pp"] == 2.0 and first["cut_complete"]
    # The final rise is still open: no cut has followed it yet.
    assert np.isnan(second["cut_pp"]) and not second["cut_complete"]


def test_hiking_cycle_liftoff_skips_a_floor():
    # Two years on a floor at 0.1, then 0.2 (below the 0.25 lift-off step), then real hikes to 3.0, then a cut.
    rate = monthly([0.1] * 24 + [0.2, 0.5, 1.5, 3.0, 2.9, 1.0, 0.5])
    row = ir.hiking_cycles(rate, threshold=1.5).iloc[0]
    assert row["trough_date"] == rate.index[0]
    assert row["liftoff_date"] == rate.index[25]  # 0.5 >= 0.1 + 0.25; the 0.2 month does not count
    assert row["peak_date"] == rate.index[27] and row["months_liftoff_to_peak"] == 2


def test_output_gap_percent_of_potential():
    gap = ir.output_gap(monthly([102.0, 97.0]), monthly([100.0, 100.0]))
    assert list(gap) == pytest.approx([2.0, -3.0])


def test_taylor_rate_hand_computed():
    infl, gap = monthly([2.0, 4.0]), monthly([0.0, -2.0])
    # pi=2, gap=0 -> 2 + 2 = 4.  pi=4, gap=-2 -> 2 + 4 + 0.5*2 + 0.5*(-2) = 6.
    assert list(ir.taylor_rate(infl, gap)) == [4.0, 6.0]
    # Raising r* by 1 raises the rule by exactly 1.
    assert list(ir.taylor_rate(infl, gap, r_star=3.0)) == [5.0, 7.0]


def test_quarterly_mean_needs_three_months():
    m = monthly([1.0, 2.0, 3.0, 4.0, 5.0])  # Jan-May: Q2 has only Apr, May
    q = ir.quarterly_mean(m)
    assert list(q.index) == [pd.Timestamp("2020-01-01")]
    assert q.iloc[0] == 2.0


def test_taylor_period_summary():
    idx = pd.date_range("2001-01-01", periods=4, freq="QS")
    frame = pd.DataFrame({"actual": [1.0, 1.0, 5.0, 5.0], "taylor": [3.0, 4.0, 4.0, 4.0]}, index=idx)
    frame["gap_pp"] = frame["actual"] - frame["taylor"]
    out = ir.taylor_period_summary(frame, {"first half": ("2001-01", "2001-06"), "all": ("2001-01", "2001-12")})
    assert list(out["quarters"]) == [2, 4]
    assert out.loc[0, "gap_pp"] == pytest.approx(-2.5)
    assert out.loc[0, "share_below_rule"] == 1.0
    assert out.loc[1, "share_below_rule"] == 0.5


# ------------------------------------------------------------------ BIS loader (stubbed HTTP)


class FakeResponse:
    def __init__(self, text):
        self.text = text


def test_bis_download_is_tidy_and_cached(tmp_path, monkeypatch):
    csv = (
        "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,TITLE\n"
        "M,GB,2020-01,0.75,x\n"
        "M,GB,2020-02,,x\n"  # missing value is dropped
        "M,JP,2020-01,-0.1,x\n"
    )
    calls = []
    monkeypatch.setattr(ir, "BIS_DIR", tmp_path)
    monkeypatch.setattr(ir, "get", lambda url, **kw: calls.append(url) or FakeResponse(csv))
    frame = ir._bis_monthly("test_cache", "WS_CBPOL", "")
    assert list(frame.columns) == ["area", "date", "value"]
    assert len(frame) == 2 and calls[0].endswith("WS_CBPOL/M." + "+".join(ir.AREAS))
    again = ir._bis_monthly("test_cache", "WS_CBPOL", "")  # served from the cache file
    assert len(calls) == 1
    assert ir._bis_series(again, "GB", "x").iloc[0] == 0.75


# ------------------------------------------------------------------ real cached data


def test_every_economy_has_long_monthly_history():
    for code in ir.AREAS:
        both = ir.economy_monthly(code)
        assert len(both) > 200, code
        assert both.index[-1] >= pd.Timestamp("2026-06-01") or code == "IN", code


def test_us_inflation_matches_levels_by_hand():
    cpi = fred.series("CPIAUCSL")
    expected = (cpi.loc["2022-03-01"] / cpi.loc["2021-03-01"] - 1) * 100
    assert ir.inflation("US").loc["2022-03-01"] == pytest.approx(expected)
    assert 8.0 < expected < 9.0


def test_us_yoy_has_no_value_across_the_missing_october_2025():
    infl = ir.inflation("US")
    assert pd.Timestamp("2025-10-01") not in infl.index
    assert pd.Timestamp("2025-11-01") in infl.index


def test_bis_series_agree_with_fred_where_both_exist():
    bis_rate = ir._bis_series(ir._bis_monthly("cbpol_monthly", "WS_CBPOL", ""), "US", "bis")
    joined = pd.concat([bis_rate, ir.policy_rate("US")], axis=1, join="inner").dropna()
    assert joined.corr().iloc[0, 1] > 0.99
    bis_cpi = ir._bis_series(ir._bis_monthly("cpi_yoy_monthly", "WS_LONG_CPI", ".771"), "US", "bis")
    joined = pd.concat([bis_cpi, ir.inflation("US")], axis=1, join="inner").dropna()
    assert (joined.iloc[:, 0] - joined.iloc[:, 1]).abs().mean() < 0.15  # seasonally adjusted vs not


def test_us_negative_real_rate_months_in_plausible_range():
    us = ir.economy_monthly("US")
    negative = int((us["real_rate"] < 0).sum())
    assert 250 < negative < 320
    spells = ir.negative_spells(us["real_rate"])
    assert spells["months"].sum() == negative


def test_us_2022_2023_hiking_cycle_peak():
    cycles = ir.hiking_cycles(ir.policy_rate("US"))
    last_rise = cycles.iloc[-1]
    assert last_rise["peak_date"] == pd.Timestamp("2023-08-01")
    assert last_rise["peak_rate"] == pytest.approx(5.33, abs=0.01)  # published monthly average
    assert last_rise["trough_date"] == pd.Timestamp("2020-04-01")
    assert last_rise["liftoff_date"] == pd.Timestamp("2022-04-01")  # funds rate 0.33 vs 0.05 at the trough
    assert last_rise["months_liftoff_to_peak"] == 16


def test_taylor_gap_is_actual_minus_rule_and_deeply_negative_in_2022():
    frame = ir.us_taylor_frame()
    assert np.allclose(frame["gap_pp"], frame["actual"] - frame["taylor"])
    assert frame.loc["2022-01-01", "gap_pp"] < -10
    # Hand check of one quarter from the stored inputs: 2022 Q1.
    row = frame.loc["2022-01-01"]
    by_hand = 2 + row["inflation"] + 0.5 * (row["inflation"] - 2) + 0.5 * row["output_gap"]
    assert row["taylor"] == pytest.approx(by_hand)


def test_taylor_frame_stops_at_last_published_gdp_quarter():
    gdp_last = fred.series("GDPC1").index[-1]
    assert ir.us_taylor_frame().index[-1] <= gdp_last
