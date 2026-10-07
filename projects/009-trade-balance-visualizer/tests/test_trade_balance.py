"""Unit tests (small frames with hand-computed answers) plus sanity checks on the cached real data."""

import numpy as np
import pandas as pd
import pytest

import trade_balance as tb
from core.http import DataUnavailable


def _index(rows):
    """rows: {(iso3, year): {column: value}} -> frame indexed by (iso3, year) like trade_frame()."""
    frame = pd.DataFrame(list(rows.values()), index=pd.MultiIndex.from_tuples(list(rows), names=["iso3", "year"]))
    return frame.sort_index()


# ------------------------------------------------------------------ World Bank side


def test_trade_frame_derived_columns_by_hand(monkeypatch):
    base = _index(
        {
            ("AAA", 2020): dict(exports=100.0, imports=80.0, exports_gdp=25.0, imports_gdp=20.0),
            ("AAA", 2021): dict(exports=90.0, imports=120.0, exports_gdp=18.0, imports_gdp=24.0),
        }
    )
    monkeypatch.setattr(tb.worldbank, "indicators", lambda codes, **kw: base.copy())
    out = tb.trade_frame()
    assert list(out["balance"]) == [20.0, -30.0]
    assert list(out["balance_gdp"]) == [5.0, -6.0]
    assert list(out["implied_gdp"]) == [400.0, 500.0]  # 100 / 0.25 and 90 / 0.18


def test_shading_series_inserts_the_crossing_point():
    exports = pd.Series([10.0, 12.0, 20.0], index=[2000, 2001, 2002])
    imports = pd.Series([14.0, 8.0, 18.0], index=[2000, 2001, 2002])
    out = tb.shading_series(exports, imports)
    # Balance -4 -> +4 between 2000 and 2001: the lines meet half way, at x=2000.5, level 11.
    assert list(out["x"]) == [2000.0, 2000.5, 2001.0, 2002.0]
    assert out.loc[1, "exports"] == out.loc[1, "imports"] == 11.0
    # No sign change between 2001 and 2002, so nothing is inserted there.
    assert len(out) == 4


def test_shading_series_skips_years_missing_either_side():
    out = tb.shading_series(pd.Series([1.0, np.nan, 3.0], index=[1, 2, 3]), pd.Series([5.0, 5.0, 5.0], index=[1, 2, 3]))
    assert list(out["x"]) == [1.0, 3.0]


def test_deficit_years_counts_runs_and_last_surplus():
    balance = pd.Series([5, -1, -2, 3, -1, -1, -4, 2], index=range(2000, 2008), dtype=float)
    result = tb.deficit_years(balance)
    assert result == {"years": 8, "surplus": 3, "deficit": 5, "longest_deficit_run": 3, "last_surplus_year": 2007}


def test_deficit_years_run_is_broken_by_a_missing_year():
    balance = pd.Series([-1.0, -1.0, -1.0], index=[2000, 2001, 2003])  # 2002 missing
    assert tb.deficit_years(balance)["longest_deficit_run"] == 2
    assert tb.deficit_years(pd.Series([-1.0, -2.0], index=[1, 2]))["last_surplus_year"] == 0


def test_latest_year_needs_enough_economies():
    rows = {(f"C{i:02d}", y): dict(balance=1.0) for i in range(10) for y in (2022, 2023)}
    rows.update({(f"C{i:02d}", 2024): dict(balance=1.0) for i in range(3)})  # a sparse newest year
    frame = _index(rows)
    assert tb.latest_year(frame, "balance", min_economies=5) == 2023
    assert tb.latest_year(frame, "balance", min_economies=2) == 2024


def test_ranking_orders_both_sides_and_applies_gdp_filter():
    frame = _index(
        {
            ("USA", 2020): dict(balance=-900.0, balance_gdp=-4.0, exports=1.0, imports=2.0, implied_gdp=2e13),
            ("CHN", 2020): dict(balance=500.0, balance_gdp=3.0, exports=3.0, imports=1.0, implied_gdp=1.5e13),
            ("DEU", 2020): dict(balance=200.0, balance_gdp=5.0, exports=3.0, imports=1.0, implied_gdp=4e12),
            ("LUX", 2020): dict(balance=30.0, balance_gdp=30.0, exports=3.0, imports=1.0, implied_gdp=1e10),
            ("FRA", 2020): dict(balance=-100.0, balance_gdp=-3.5, exports=3.0, imports=1.0, implied_gdp=3e12),
        }
    )
    surplus, deficit = tb.ranking(frame, 2020, "balance", 2)
    assert list(surplus["country"]) == ["China", "Germany"]
    assert list(deficit["country"]) == ["United States", "France"]
    surplus, _ = tb.ranking(frame, 2020, "balance_gdp", 2)
    assert surplus["country"].iloc[0] == "Luxembourg"
    surplus, _ = tb.ranking(frame, 2020, "balance_gdp", 2, min_gdp=1e11)  # the filter drops Luxembourg
    assert list(surplus["country"]) == ["Germany", "China"]


def test_coverage_reports_years_economies_and_latest_full_year():
    frame = _index({("AAA", 1990): {k: 1.0 for k in tb.INDICATORS}, ("BBB", 1995): {k: 2.0 for k in tb.INDICATORS}})
    frame["exports"] = [1.0, np.nan]  # BBB has no exports
    cov = tb.coverage(frame, min_economies=1).set_index("indicator")
    assert tuple(cov.loc["exports", ["first_year", "last_year", "economies", "latest_full_year"]]) == (1990, 1990, 1, 1990)
    assert tuple(cov.loc["imports", ["first_year", "last_year", "economies", "latest_full_year"]]) == (1990, 1995, 2, 1995)
    assert tb.coverage(frame).loc[0, "latest_full_year"] == 0  # never 150 economies in a year


# ------------------------------------------------------------------ WITS parsing and loader (stubbed HTTP)


def sdmx_payload(partners, years, series):
    """Minimal SDMX-JSON like WITS returns. series: {partner_index: {year_index: value}}."""
    return {
        "dataSets": [
            {"series": {f"0:0:{p}:0:0": {"observations": {str(t): [v, 0] for t, v in obs.items()}} for p, obs in series.items()}}
        ],
        "structure": {
            "dimensions": {
                "series": [
                    {"id": "FREQ", "values": [{"id": "A"}]},
                    {"id": "REPORTER", "values": [{"id": "USA"}]},
                    {"id": "PARTNER", "values": [{"id": p} for p in partners]},
                    {"id": "PRODUCTCODE", "values": [{"id": "Total"}]},
                    {"id": "INDICATOR", "values": [{"id": "XPRT-TRD-VL"}]},
                ],
                "observation": [{"id": "TIME_PERIOD", "values": [{"id": str(y)} for y in years]}],
            }
        },
    }


def test_parse_wits_json_by_hand():
    payload = sdmx_payload(["AAA", "BBB"], [2019, 2020], {0: {0: 100.0, 1: 150.0}, 1: {1: 40.5}})
    out = tb.parse_wits_json(payload, "exports")
    got = {(r.partner, r.year): r.value_usd_k for r in out.itertuples()}
    assert got == {("AAA", 2019): 100.0, ("AAA", 2020): 150.0, ("BBB", 2020): 40.5}
    assert set(out["flow"]) == {"exports"}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = b""

    def json(self):
        return self._payload


def test_partner_trade_downloads_filters_rounds_and_caches(tmp_path, monkeypatch):
    payload = sdmx_payload(["AAA", "EAS", "999", "WLD"], [2020], {0: {0: 100.4}, 1: {0: 7.0}, 2: {0: 1.0}, 3: {0: 100.4}})
    calls = []
    monkeypatch.setattr(tb, "WITS_DIR", tmp_path)
    monkeypatch.setattr(tb, "get", lambda url, **kw: calls.append(url) or FakeResponse(payload))
    monkeypatch.setattr(tb, "wits_countries", lambda **kw: pd.DataFrame({"iso3": ["AAA", "EAS", "WLD"], "name": ["A", "East Asia", "World"], "is_group": [False, True, True]}))
    out = tb.partner_trade("usa")
    assert len(calls) == 2 and "reporter/usa/year/all/partner/all/product/Total" in calls[0]
    assert {u.split("indicator/")[1] for u in calls} == {"XPRT-TRD-VL", "MPRT-TRD-VL"}
    assert set(out["partner"]) == {"AAA", "WLD"}  # region aggregate and code 999 dropped, world total kept
    assert set(out["value_usd_k"]) == {100.0}
    assert (tmp_path / "USA.csv.gz").exists()
    again = tb.partner_trade("USA")  # from cache
    assert len(calls) == 2 and len(again) == len(out)


def test_partner_trade_raises_when_nothing_comes_back(tmp_path, monkeypatch):
    payload = sdmx_payload(["AAA"], [2020], {})
    monkeypatch.setattr(tb, "WITS_DIR", tmp_path)
    monkeypatch.setattr(tb, "get", lambda url, **kw: FakeResponse(payload))
    monkeypatch.setattr(tb, "wits_countries", lambda **kw: pd.DataFrame({"iso3": ["AAA"], "name": ["A"], "is_group": [False]}))
    with pytest.raises(DataUnavailable):
        tb.partner_trade("zzz")


# ------------------------------------------------------------------ partner analysis on a small frame


@pytest.fixture
def small_trade(monkeypatch):
    monkeypatch.setattr(tb, "partner_names", lambda: {"AAA": "Alpha", "BBB": "Beta", "CCC": "Gamma", "UNS": "Unspecified"})
    rows = []
    for partner, exp, imp in [("AAA", 600, 200), ("BBB", 300, 400), ("CCC", 100, 400), ("UNS", 100, 0), ("WLD", 1100, 1000)]:
        rows.append((2020, "exports", partner, float(exp)))
        rows.append((2020, "imports", partner, float(imp)))
    return pd.DataFrame(rows, columns=["year", "flow", "partner", "value_usd_k"])


def test_top_partners_shares_use_the_world_total(small_trade):
    out = tb.top_partners(small_trade, 2020, "exports", 3)
    assert list(out["partner"]) == ["AAA", "BBB", "CCC"]  # the unspecified row is not a partner
    assert out["value_usd"].iloc[0] == 600 * 1000
    assert out["share"].iloc[0] == pytest.approx(600 / 1100 * 100)
    assert out["cumulative_share"].iloc[-1] == pytest.approx(1000 / 1100 * 100)


def test_bilateral_balance_by_hand(small_trade):
    out = tb.bilateral_balance(small_trade, 2020)
    assert list(out["partner"]) == ["AAA", "BBB", "CCC"]
    assert list(out["balance"]) == [400 * 1000, -100 * 1000, -300 * 1000]
    assert list(out["total_trade"]) == [800 * 1000, 700 * 1000, 500 * 1000]


def test_concentration_by_hand(small_trade):
    result = tb.concentration(small_trade, 2020, "exports")
    assert result["top1_share"] == pytest.approx(60.0)
    assert result["top5_share"] == pytest.approx(100.0)
    assert result["hhi"] == pytest.approx(60**2 + 30**2 + 10**2)


def test_world_totals_balance(small_trade):
    w = tb.world_totals(small_trade).loc[2020]
    assert (w["exports"], w["imports"], w["balance"]) == (1100 * 1000, 1000 * 1000, 100 * 1000)


# ------------------------------------------------------------------ real cached data


@pytest.fixture(scope="module")
def frame():
    return tb.trade_frame()


def test_world_bank_coverage_floors(frame):
    cov = tb.coverage(frame).set_index("indicator")
    assert (cov["economies"] >= 190).all()
    assert (cov["first_year"] <= 1970).all()
    assert (cov["latest_full_year"] >= 2023).all()
    assert tb.latest_year(frame) >= 2023


def test_us_balance_identities_and_record(frame):
    us = tb.economy(frame, "USA")
    assert us.loc[2023, "balance"] == pytest.approx(us.loc[2023, "exports"] - us.loc[2023, "imports"])
    assert us.loc[2023, "balance_gdp"] == pytest.approx(us.loc[2023, "exports_gdp"] - us.loc[2023, "imports_gdp"])
    record = tb.deficit_years(us["balance"])
    assert record["last_surplus_year"] == 1975  # deficit every year since
    assert record["longest_deficit_run"] >= 49


def test_implied_gdp_matches_known_us_gdp(frame):
    gdp_2023 = tb.economy(frame, "USA").loc[2023, "implied_gdp"]
    assert 27e12 < gdp_2023 < 28.5e12  # US nominal GDP 2023 was about US$27.7 trillion


def test_national_accounts_balance_close_to_balance_of_payments_for_the_us(frame):
    us = tb.economy(frame, "USA").dropna(subset=["net_bop"])
    gap = (us["balance"] - us["net_bop"]).abs() / us["implied_gdp"]
    assert gap.loc[2000:].max() < 0.01  # within 1% of GDP in every year since 2000


def test_rankings_put_known_extremes_on_the_right_side(frame):
    year = tb.latest_year(frame)
    surplus, deficit = tb.ranking(frame, year, "balance", 5)
    assert deficit["country"].iloc[0] == "United States" and deficit["balance"].iloc[0] < -5e11
    assert "China" in list(surplus["country"]) and (surplus["balance"] > 0).all() and (deficit["balance"] < 0).all()


# --- WITS cache


@pytest.fixture(scope="module")
def usa():
    return tb.partner_trade("USA")


def test_wits_partner_rows_sum_to_the_world_total(usa):
    for flow in ("exports", "imports"):
        sub = usa[(usa["year"] == 2020) & (usa["flow"] == flow)]
        world = sub.loc[sub["partner"] == tb.WORLD, "value_usd_k"].iloc[0]
        countries = sub.loc[sub["partner"] != tb.WORLD, "value_usd_k"].sum()
        assert countries == pytest.approx(world, rel=1e-6)


def test_us_exports_to_canada_in_2020_by_hand(usa):
    canada = usa[(usa["year"] == 2020) & (usa["flow"] == "exports") & (usa["partner"] == "CAN")]["value_usd_k"].iloc[0]
    assert canada / 1e6 == pytest.approx(255.0, abs=1.0)  # US$ 255.0 billion
    assert tb.world_totals(usa).loc[2020, "exports"] / 1e9 == pytest.approx(1430.3, abs=1.0)


def test_us_top_export_partners_2023(usa):
    top = tb.top_partners(usa, 2023, "exports", 3)
    assert list(top["partner"]) == ["CAN", "MEX", "CHN"]
    assert 16 < top["share"].iloc[0] < 19


def test_china_runs_a_large_merchandise_surplus_with_the_us(usa):
    chn = tb.partner_trade("CHN")
    bb = tb.bilateral_balance(chn, 2023).set_index("partner")
    assert bb.loc["USA", "balance"] > 250e9
    assert bb.index[0] in {"USA", "HKG"}  # the two largest bilateral surpluses


def test_canada_exports_are_highly_concentrated_on_the_us():
    can = tb.partner_trade("CAN")
    assert tb.concentration(can, 2023, "exports")["top1_share"] > 70


def test_every_reporter_has_a_long_history_and_world_rows():
    for reporter in tb.WITS_REPORTERS:
        trade = tb.partner_trade(reporter)
        years = tb.wits_years(trade)
        assert years[0] <= 1996 and years[-1] >= 2021, reporter
        assert {"exports", "imports"} == set(trade["flow"]), reporter
        assert (trade["partner"] == tb.WORLD).any(), reporter


def test_wits_merchandise_is_a_share_of_world_bank_goods_and_services(frame, usa):
    wits_exports = tb.world_totals(usa).loc[2020, "exports"]
    wb_exports = tb.economy(frame, "USA").loc[2020, "exports"]
    assert 0.5 < wits_exports / wb_exports < 1.0  # goods are most of, but not all of, goods and services
