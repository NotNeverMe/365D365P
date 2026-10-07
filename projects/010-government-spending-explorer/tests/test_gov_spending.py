"""Unit tests for gov_spending: synthetic frames with hand-computed answers, then checks on the cached data."""

import math

import numpy as np
import pandas as pd
import pytest

import gov_spending as gs


def frame(rows: dict[tuple[str, int], dict[str, float]]) -> pd.DataFrame:
    """Wide (iso3, year) frame with every series column present (NaN where not given)."""
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = pd.MultiIndex.from_tuples(df.index, names=["iso3", "year"])
    for s in gs.SERIES:
        if s.key not in df:
            df[s.key] = np.nan
    return df.sort_index()


@pytest.fixture
def toy() -> pd.DataFrame:
    return frame(
        {
            ("USA", 2020): {"expense": 40.0, "interest": 10.0, "compensation": 20.0, "goods_services": 15.0, "transfers": 40.0, "other": 15.0, "education": 5.0},
            ("USA", 2021): {"expense": 30.0, "interest": 20.0},
            ("DEU", 2021): {"expense": 50.0, "interest": 5.0, "education": 4.0},
            ("FRA", 2021): {"interest": 8.0},
            ("GBR", 2019): {"expense": 35.0, "interest": 12.0},
        }
    )


def test_economic_in_gdp_multiplies_share_by_expense(toy):
    out = gs.economic_in_gdp(toy)
    assert out.loc[("USA", 2020), "interest_gdp"] == pytest.approx(4.0)  # 10% of a 40%-of-GDP budget
    assert out.loc[("USA", 2020), "compensation_gdp"] == pytest.approx(8.0)
    assert math.isnan(out.loc[("FRA", 2021), "interest_gdp"])  # no expense figure, so no conversion


def test_economic_sum_check_only_uses_rows_with_all_five(toy):
    sums = gs.economic_sum_check(toy)
    assert list(sums.index) == [("USA", 2020)]
    assert sums.iloc[0] == pytest.approx(20 + 15 + 10 + 40 + 15)


def test_broad_year_is_latest_year_meeting_threshold(toy):
    # interest: 2019 -> 1 country, 2020 -> 1, 2021 -> 3
    assert gs.broad_year(toy, "interest", min_countries=3) == 2021
    assert gs.broad_year(toy, "interest", min_countries=1) == 2021
    with pytest.raises(ValueError):
        gs.broad_year(toy, "interest", min_countries=4)


def test_latest_on_or_before_respects_lag_and_reports_year(toy):
    assert gs.latest_on_or_before(toy, "interest", "USA", 2021) == (20.0, 2021)
    assert gs.latest_on_or_before(toy, "education", "USA", 2021, max_lag=0)[1] is None
    value, year = gs.latest_on_or_before(toy, "education", "USA", 2021, max_lag=1)
    assert (value, year) == (5.0, 2020)
    assert gs.latest_on_or_before(toy, "interest", "GBR", 2021, max_lag=1)[1] is None  # 2019 is two years back
    assert gs.latest_on_or_before(toy, "interest", "XXX", 2021)[1] is None


def test_snapshot_has_one_row_per_series_and_keeps_gaps(toy):
    snap = gs.snapshot(toy, "USA", 2021, max_lag=1)
    assert list(snap["key"]) == [s.key for s in gs.SERIES]
    row = snap.set_index("key")
    assert row.loc["expense", "value"] == 30.0 and row.loc["expense", "observation_year"] == 2021
    assert row.loc["education", "value"] == 5.0 and row.loc["education", "observation_year"] == 2020
    assert math.isnan(row.loc["military", "value"]) and pd.isna(row.loc["military", "observation_year"])
    assert row.loc["interest", "denominator"] == gs.EXPENSE and row.loc["education", "denominator"] == gs.GDP


def test_cross_section_sorted_descending_and_empty_for_missing_year(toy):
    sec = gs.cross_section(toy, "interest", 2021)
    assert list(sec["iso3"]) == ["USA", "FRA", "DEU"]
    assert list(sec["value"]) == [20.0, 8.0, 5.0]
    assert gs.cross_section(toy, "interest", 1800).empty


def test_interest_ranking_derives_gdp_share(toy):
    rank = gs.interest_ranking(toy, 2021, top=2)
    assert list(rank["iso3"]) == ["USA", "FRA"]
    assert rank.loc[0, "interest_gdp"] == pytest.approx(0.20 * 30.0)  # 6.0% of GDP
    assert math.isnan(rank.loc[1, "interest_gdp"])


def test_trend_filters_countries_and_years(toy):
    long = gs.trend(toy, ["interest"], ["USA", "GBR"], 2020, 2021)
    assert set(zip(long["iso3"], long["year"])) == {("USA", 2020), ("USA", 2021)}
    assert (long["indicator"] == "Interest payments").all()


def test_median_by_year_counts_reporters(toy):
    med = gs.median_by_year(toy, ["interest"])
    assert med.loc[2021, "interest_median"] == 8.0 and med.loc[2021, "interest_n"] == 3


def test_coverage_reports_first_last_and_countries(toy):
    cov = gs.coverage(toy).set_index("series")
    row = cov.loc["Interest payments"]
    assert (row["first_year"], row["last_year"], row["countries"]) == (2019, 2021, 4)
    assert row["best_year"] == 2021 and row["countries_in_best_year"] == 3


# ------------------------------------------------------------------------------------- COFOG

CSV = """DATAFLOW,LAST UPDATE,freq,unit,sector,cofog99,na_item,geo,TIME_PERIOD,OBS_VALUE,OBS_FLAG,CONF_STATUS
X,d,A,PC_GDP,S13,GF01,TE,EL,2022,10.0,p,
X,d,A,PC_GDP,S13,GF0101,TE,EL,2022,3.0,,
X,d,A,PC_GDP,S13,GF07,TE,EL,2022,5.0,,
X,d,A,PC_GDP,S13,TOTAL,TE,EL,2022,15.0,,
X,d,A,PC_TOT,S13,GF01,TE,EL,2022,66.7,,
X,d,A,PC_TOT,S13,GF07,TE,EL,2022,33.3,,
X,d,A,PC_GDP,S13,GF01,TE,EA20,2022,9.0,,
X,d,A,PC_GDP,S13,GF01,TE,DE,2022,,,
"""


def test_parse_cofog_maps_countries_and_drops_aggregates_subdivisions_and_blanks():
    out = gs.parse_cofog(CSV)
    assert set(out["iso3"]) == {"GRC"}  # EL -> GRC; EA20 (aggregate) and the blank German value dropped
    assert "GF0101" not in set(out["cofog"])
    assert set(out["unit"]) == {"pc_gdp", "pc_total"}
    assert out.loc[(out["cofog"] == "GF01") & (out["unit"] == "pc_gdp"), "flag"].iloc[0] == "p"


def test_cofog_snapshot_and_total_on_parsed_data():
    out = gs.parse_cofog(CSV)
    shot = gs.cofog_snapshot(out, "GRC", 2022)
    assert list(shot["cofog"]) == ["GF01", "GF07"]  # only divisions that exist, in COFOG order
    assert shot.set_index("cofog").loc["GF07", "pc_gdp"] == 5.0
    assert shot.set_index("cofog").loc["GF01", "pc_total"] == 66.7
    assert gs.cofog_total(out, "GRC", 2022) == 15.0
    assert gs.cofog_snapshot(out, "GRC", 1999).empty
    assert math.isnan(gs.cofog_total(out, "FRA", 2022))


# ----------------------------------------------------------------------------- real cached data


@pytest.fixture(scope="module")
def real() -> pd.DataFrame:
    return gs.load()


def test_real_data_has_every_series_with_substantial_coverage(real):
    assert set(real.columns) == {s.key for s in gs.SERIES}
    assert real["interest"].notna().sum() > 3000
    assert real["education"].notna().sum() > 4000
    assert real.index.get_level_values("iso3").nunique() > 180


def test_real_loader_passes_world_bank_values_through_unchanged(real):
    from core import worldbank as wb

    raw = wb.indicator("GC.XPN.INTP.ZS").set_index(["iso3", "year"])["value"]
    assert real.loc[("USA", 2022), "interest"] == pytest.approx(raw[("USA", 2022)])


def test_real_economic_shares_mostly_add_to_100(real):
    sums = gs.economic_sum_check(real)
    assert len(sums) > 2500
    assert ((sums - 100).abs() <= 1.0).mean() > 0.8  # 82.9% when this was written


def test_real_interest_ranking_2022_is_led_by_sri_lanka(real):
    # Verified against the cached World Bank series: Sri Lanka 41.3% of expense, 6.5% of GDP in 2022.
    rank = gs.interest_ranking(real, 2022, top=3)
    assert rank.loc[0, "iso3"] == "LKA"
    assert rank.loc[0, "interest_share"] == pytest.approx(41.3, abs=0.1)
    assert rank.loc[0, "interest_gdp"] == pytest.approx(6.5, abs=0.1)
    assert list(rank["interest_share"]) == sorted(rank["interest_share"], reverse=True)


def test_real_broad_year_for_interest_is_2022(real):
    assert gs.broad_year(real, "interest") == 2022


def test_real_cofog_divisions_sum_to_the_reported_total():
    cofog = gs.load_cofog()
    assert cofog["iso3"].nunique() == 30
    divisions = cofog[cofog["cofog"] != "TOTAL"]
    # Shares of total expenditure add up to 100 (rounding only).
    shares = divisions[divisions["unit"] == "pc_total"].groupby(["iso3", "year"])["value"].sum()
    assert (shares - 100).abs().max() < 1.0
    # % of GDP divisions add up to the reported total within rounding of ten one-decimal numbers.
    gdp_sum = divisions[divisions["unit"] == "pc_gdp"].groupby(["iso3", "year"])["value"].sum()
    total = cofog[(cofog["cofog"] == "TOTAL") & (cofog["unit"] == "pc_gdp")].set_index(["iso3", "year"])["value"]
    joined = pd.concat([gdp_sum.rename("sum"), total.rename("total")], axis=1).dropna()
    assert len(joined) > 800
    assert (joined["sum"] - joined["total"]).abs().max() < 0.5


def test_real_cofog_germany_2022_social_protection():
    # Hand-checked against the Eurostat download: 19.8% of GDP, total 48.6%.
    cofog = gs.load_cofog()
    shot = gs.cofog_snapshot(cofog, "DEU", 2022).set_index("cofog")
    assert shot.loc["GF10", "pc_gdp"] == pytest.approx(19.8)
    assert gs.cofog_total(cofog, "DEU", 2022) == pytest.approx(48.6)
