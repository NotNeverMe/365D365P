"""Unit tests for cost_of_living: synthetic frames with hand-computed answers, plus checks on the cached data."""

import pandas as pd
import pytest

import cost_of_living as col
from core import bigmac

# A miniature file in BEA's MARPP layout: quoted FIPS codes, (NA) cells, a name without parentheses,
# a starred name, the national and non-metropolitan rows, and trailing footnote lines.
BEA_SAMPLE = """GeoFIPS,GeoName,Region,TableName,LineCode,IndustryClassification,Description,Unit,2022,2023
 "00000","United States", ,MARPP,1,"...","RPPs: All items ","Index",100.000,100.000
 "00999","United States (Nonmetropolitan Portion) *", ,MARPP,1,"...","RPPs: All items ","Index",88.000,88.500
 "10180","Abilene, TX (Metropolitan Statistical Area)", ,MARPP,1,"...","RPPs: All items ","Index",90.000,91.000
 "10180","Abilene, TX (Metropolitan Statistical Area)", ,MARPP,3,"...","RPPs: Services: Housing ","Index",70.000,72.000
 "14860","Bridgeport-Stamford-Danbury, CT Metropolitan Statistical Area", ,MARPP,1,"...","RPPs: All items ","Index",110.000,108.000
 "21420","Enid, OK (Metropolitan Statistical Area) *", ,MARPP,1,"...","RPPs: All items ","Index",(NA),85.500
Note: See the included footnote file.,,,,,,,,,
U.S. Bureau of Economic Analysis,,,,,,,,,
"""


@pytest.fixture(scope="module")
def sample():
    return col.parse_bea(BEA_SAMPLE)


def test_parse_bea_keeps_only_metros_and_real_values(sample):
    assert set(sample["geo_fips"]) == {"10180", "14860", "21420"}
    # Abilene: 2 components x 2 years = 4; Bridgeport: 2; Enid: 1 (its 2022 value is (NA) and is dropped)
    assert len(sample) == 4 + 2 + 1
    assert not sample["rpp"].isna().any()


def test_parse_bea_cleans_names_and_maps_components(sample):
    assert set(sample["metro"]) == {"Abilene, TX", "Bridgeport-Stamford-Danbury, CT", "Enid, OK"}
    abilene = sample[(sample["metro"] == "Abilene, TX") & (sample["year"] == 2023)].set_index("component")["rpp"]
    assert abilene.to_dict() == {"All items": 91.0, "Housing": 72.0}


def test_metro_panel_shape(sample):
    panel = col.metro_panel(sample)
    assert panel.index.names == ["place", "year"]
    assert list(panel.columns) == list(col.BEA_COMPONENTS.values())
    assert panel.loc[("Abilene, TX", 2022), "Housing"] == 70.0
    assert pd.isna(panel.loc[("Bridgeport-Stamford-Danbury, CT", 2022), "Housing"])


# ---------------------------------------------------------------- arithmetic


def test_equivalent_salary_is_proportional_to_price_ratio():
    assert col.equivalent_salary(60_000, 100, 125) == pytest.approx(75_000)
    assert col.equivalent_salary(60_000, 125, 100) == pytest.approx(48_000)
    assert col.equivalent_salary(60_000, 80, 80) == pytest.approx(60_000)


def test_equivalent_salary_round_trips():
    there = col.equivalent_salary(52_000, 93.2, 141.7)
    assert col.equivalent_salary(there, 141.7, 93.2) == pytest.approx(52_000)


@pytest.mark.parametrize("a, b", [(0, 100), (100, 0), (-5, 100), (100, -1)])
def test_relative_price_rejects_non_positive_index(a, b):
    with pytest.raises(ValueError):
        col.relative_price(a, b)


# ---------------------------------------------------------------- generic panel helpers


@pytest.fixture
def panel():
    index = pd.MultiIndex.from_product([["Alpha", "Beta", "Gamma"], [2020, 2021]], names=["place", "year"])
    data = {"x": [100, 110, 80, 88, 120, 114], "y": [100, 100, 60, 66, None, None]}
    return pd.DataFrame(data, index=index)


def test_snapshot_and_comparison(panel):
    snap = col.snapshot(panel, 2021)
    assert list(snap.index) == ["Alpha", "Beta", "Gamma"]
    cmp = col.comparison(snap, "Alpha", "Beta")
    assert cmp.loc["x", "B_vs_A_pct"] == pytest.approx(-20.0)  # 88 / 110 - 1
    assert cmp.loc["y", "B_vs_A_pct"] == pytest.approx(-34.0)  # 66 / 100 - 1
    # Gamma has no 'y', so that measure is dropped rather than shown as NaN
    assert list(col.comparison(snap, "Alpha", "Gamma").index) == ["x"]
    with pytest.raises(KeyError):
        col.comparison(snap, "Alpha", "Nowhere")


def test_rank_table_orders_most_expensive_first(panel):
    ranked = col.rank_table(col.snapshot(panel, 2021), "x")
    assert list(ranked["place"]) == ["Gamma", "Alpha", "Beta"]  # 114, 110, 88
    assert list(ranked["rank"]) == [1, 2, 3]
    assert ranked["vs_100"].tolist() == pytest.approx([14, 10, -12])
    assert len(col.rank_table(col.snapshot(panel, 2021), "y")) == 2  # missing values are left out


def test_change_between(panel):
    change = col.change_between(panel, "x", 2020, 2021).set_index("place")
    assert change.loc["Alpha", "change"] == pytest.approx(10)
    assert change.loc["Alpha", "change_pct"] == pytest.approx(10.0)
    assert change.loc["Gamma", "change"] == pytest.approx(-6)
    assert change.index[0] == "Alpha"  # largest rise first
    assert "Gamma" not in col.change_between(panel, "y", 2020, 2021)["place"].tolist()
    with pytest.raises(KeyError):
        col.change_between(panel, "x", 1999, 2021)


def test_history_filters_places_and_drops_missing(panel):
    hist = col.history(panel, ["Alpha", "Gamma"], "y")
    assert sorted(hist["place"].unique()) == ["Alpha"]
    assert hist["value"].tolist() == [100, 100]


def test_latest_year_needs_enough_places(panel):
    assert col.latest_year(panel, "x", min_places=3) == 2021
    assert col.latest_year(panel, "y", min_places=3) == 2021  # nothing qualifies: falls back to the last year present


def test_spread_and_agreement():
    snap = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0], "c": [4.0, 3.0, 2.0, 1.0]})
    sp = col.spread(snap)
    assert sp.loc["a", "min"] == 1 and sp.loc["a", "max"] == 4
    assert sp.loc["b", "corr_with_all_items"] == pytest.approx(1.0)
    assert sp.loc["c", "corr_with_all_items"] == pytest.approx(-1.0)
    agree = col.measure_agreement(snap, "a", "b")
    assert agree["n"] == 4 and agree["spearman"] == pytest.approx(1.0) and agree["median_ratio"] == pytest.approx(2.0)


# ---------------------------------------------------------------- cached BEA data


@pytest.fixture(scope="module")
def bea():
    return col.load_bea()


@pytest.fixture(scope="module")
def metros(bea):
    return col.metro_panel(bea)


def test_bea_coverage(bea):
    assert bea["geo_fips"].nunique() == 387
    assert bea["metro"].nunique() == 387  # names are unique, so they can serve as keys
    assert (bea["year"].min(), bea["year"].max()) == (2008, 2024)
    assert set(bea["component"]) == set(col.BEA_COMPONENTS.values())
    assert not bea["metro"].str.contains("Metropolitan|\\*").any()
    assert bea["rpp"].between(30, 300).all()  # extremes are real: Honolulu utilities 2008 is 266


def test_bea_known_values(metros):
    # Read off the BEA file by hand: 2024 all-items RPPs.
    snap = col.snapshot(metros, 2024)
    assert snap.loc["San Francisco-Oakland-Fremont, CA", "All items"] == pytest.approx(115.613)
    assert snap.loc["New York-Newark-Jersey City, NY-NJ", "All items"] == pytest.approx(112.563)
    assert snap.loc["Dallas-Fort Worth-Arlington, TX", "All items"] == pytest.approx(103.090)
    assert snap.loc["Monroe, LA", "All items"] == pytest.approx(83.597)
    ranked = col.rank_table(snap, "All items")
    assert ranked.iloc[0]["place"] == "San Francisco-Oakland-Fremont, CA"
    assert ranked.iloc[-1]["place"] == "Monroe, LA"


def test_new_york_to_dallas_salary(metros):
    snap = col.snapshot(metros, 2024)
    # 100,000 * 103.090 / 112.563 = 91,584.7
    result = col.equivalent_salary(100_000, snap.loc["New York-Newark-Jersey City, NY-NJ", "All items"], snap.loc["Dallas-Fort Worth-Arlington, TX", "All items"])
    assert result == pytest.approx(91_584.7, abs=1)


def test_housing_drives_the_variation_between_metros(metros):
    sp = col.spread(col.snapshot(metros, 2024))
    assert sp.loc["Housing", "p90_minus_p10"] > 3 * sp.loc["Goods", "p90_minus_p10"]
    assert sp.loc["Housing", "corr_with_all_items"] > 0.9


def test_late_starting_metros_have_no_early_values(metros):
    assert ("Enid, OK", 2012) not in metros.index  # BEA has no estimate for Enid before 2013
    assert ("Enid, OK", 2013) in metros.index


# ---------------------------------------------------------------- countries


@pytest.fixture(scope="module")
def table():
    return col.country_table()


def test_bigmac_levels_are_us_relative_and_drop_the_euro_area():
    levels = col.bigmac_levels()
    assert "EUZ" not in set(levels["iso3"])
    assert levels.loc[levels["iso3"] == "USA", "bigmac"].eq(100).all()
    # The Economist's USD_raw is price / US price - 1, so level = 100 * (USD_raw + 1). Compare with an independent route.
    raw = bigmac.load()
    che = raw[(raw["iso_a3"] == "CHE") & (raw["date"].dt.year == 2024)]
    expected = ((che["USD_raw"] + 1) * 100).mean()
    assert levels[(levels["iso3"] == "CHE") & (levels["year"] == 2024)]["bigmac"].iloc[0] == pytest.approx(expected, rel=1e-4)


def test_country_table_coverage_and_values(table):
    assert table["iso3"].nunique() > 200
    assert table["year"].min() <= 2000 and table["year"].max() >= 2024
    usa = table[table["iso3"] == "USA"]
    assert usa["household"].dropna().eq(100).all() and usa["gdp"].dropna().eq(100).all()
    assert usa["bigmac"].dropna().eq(100).all()
    che = table[(table["iso3"] == "CHE") & (table["year"] == 2024)].iloc[0]
    assert che["household"] == pytest.approx(125.756, abs=0.01)  # World Bank figure read from the cached file
    assert che["household"] > che["gdp"]  # households face higher prices than the economy as a whole


def test_country_panel_and_latest_year(table):
    panel = col.country_panel(table)
    assert panel.index.names == ["place", "year"]
    year = col.latest_year(panel, "household")
    assert year >= 2023
    assert col.snapshot(panel, year)["household"].notna().sum() >= 150


def test_household_prices_rise_with_the_big_mac_across_countries(table):
    snap = col.snapshot(col.country_panel(table), 2024)
    agree = col.measure_agreement(snap)
    assert agree["n"] > 40
    assert agree["spearman"] > 0.6


def test_poorest_countries_are_cheaper_than_switzerland(table):
    snap = col.snapshot(col.country_panel(table), 2024)
    assert snap.loc["India", "household"] < 40 < 100 < snap.loc["Switzerland", "household"]
