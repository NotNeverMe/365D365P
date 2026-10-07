"""Unit tests for unemployment: small hand-computed frames, then sanity checks on the cached World Bank data."""

import numpy as np
import pandas as pd
import pytest

import unemployment as un

COLUMNS = list(un.INDICATORS) + ["gender_gap", "youth_ratio", "education_gap"]


def make_frame(rows):
    """rows: {(iso3, year): {column: value}} -> sorted frame indexed by (iso3, year) with every column present."""
    df = pd.DataFrame.from_dict(rows, orient="index").reindex(columns=COLUMNS)
    df.index = pd.MultiIndex.from_tuples(df.index, names=["iso3", "year"])
    df["gender_gap"] = df["female"] - df["male"]
    df["youth_ratio"] = df["youth"] / df["total"]
    df["education_gap"] = df["basic"] - df["advanced"]
    return df.sort_index()


EDU = {"basic": 10.0, "intermediate": 6.0, "advanced": 4.0, "total": 7.0}


@pytest.fixture
def toy():
    return make_frame(
        {
            ("AAA", 2020): {**EDU, "female": 8.0, "male": 6.0, "youth": 14.0},
            ("AAA", 2022): {"basic": 9.0, "intermediate": 5.0, "advanced": 8.0, "total": 6.0, "female": 5.0, "male": 7.0, "youth": 12.0},
            ("BBB", 2018): {**EDU, "female": 3.0, "male": 3.0, "youth": 9.0},
            ("BBB", 2022): {"total": 4.0, "female": 4.0, "male": 4.0, "youth": 8.0},  # no education data this year
            ("CCC", 2022): {"basic": 5.0, "intermediate": 4.0, "total": 5.0, "female": 6.0, "male": 4.0, "youth": 15.0},  # advanced missing
            ("DDD", 2010): {**EDU, "female": 5.0, "male": 5.0, "youth": 10.0},  # too old to stand in for 2022
        }
    )


def test_derived_measures_have_the_documented_signs_and_units(toy):
    row = toy.loc[("AAA", 2020)]
    assert row["gender_gap"] == 2.0  # female minus male: women worse off
    assert row["youth_ratio"] == pytest.approx(14.0 / 7.0)
    assert row["education_gap"] == 6.0  # basic minus advanced: the less educated worse off
    assert toy.loc[("AAA", 2022), "education_gap"] == pytest.approx(1.0)
    assert np.isnan(toy.loc[("BBB", 2022), "education_gap"])


def test_coverage_table_counts(toy):
    table = un.coverage_table(toy, n_economies=8).set_index("indicator")
    total = table.loc["SL.UEM.TOTL.ZS"]
    # total is reported for AAA (2 years), BBB (2), CCC (1), DDD (1): 4 economies, 6 observations
    assert (total["economies"], total["observations"]) == (4, 6)
    assert total["share_of_economies_pct"] == pytest.approx(50.0)
    assert (total["first_year"], total["last_year"]) == (2010, 2022)
    assert total["median_years_per_economy"] == pytest.approx(1.5)
    adv = table.loc["SL.UEM.ADVN.ZS"]  # AAA 2020, 2022; BBB 2018; DDD 2010
    assert (adv["economies"], adv["observations"], adv["economies_with_10plus_years"]) == (3, 4, 0)


def test_economies_per_year_and_complete_education_count(toy):
    per_year = un.economies_per_year(toy, ["total", "advanced"])
    assert per_year.loc[2022].to_dict() == {"total": 3, "advanced": 1}
    assert un.education_complete_count(toy, 2022) == 1  # only AAA has all three; CCC lacks advanced
    assert un.education_complete_count(toy, 1999) == 0


def test_default_year_skips_years_with_thin_education_coverage():
    rows = {}
    for year, n_with_edu in ((2020, 10), (2021, 8), (2022, 2)):
        for i in range(10):
            rows[(f"C{i}", year)] = {"total": 5.0, **({k: 5.0 for k in un.EDUCATION} if i < n_with_edu else {})}
    assert un.default_year(make_frame(rows)) == 2021  # 8 >= 75% of 10, but 2 is not


def test_education_snapshot_uses_latest_complete_record_within_window(toy):
    snap = un.education_snapshot(toy, 2022, max_age=5, names={"AAA": "Alpha"}).set_index("iso3")
    assert set(snap.index) == {"AAA", "BBB"}  # CCC incomplete, DDD too old
    assert snap.loc["AAA", "year_used"] == 2022 and snap.loc["BBB", "year_used"] == 2018
    assert snap.loc["AAA", "country"] == "Alpha"
    assert snap.loc["AAA", "education_gap"] == pytest.approx(1.0)
    exact = un.education_snapshot(toy, 2022, max_age=0)
    assert list(exact["iso3"]) == ["AAA"]
    assert un.education_snapshot(toy, 1995).empty


def test_education_profile_exact_year_fallback_and_nothing(toy):
    year_used, profile = un.education_profile(toy, "AAA", 2022)
    assert year_used == 2022 and profile["advanced"] == 8.0
    year_used, profile = un.education_profile(toy, "AAA", 2021)  # no 2021 record: falls back to 2020
    assert year_used == 2020 and profile["basic"] == 10.0
    year_used, profile = un.education_profile(toy, "BBB", 2022)  # 2022 has no education rate, 2018 is within 5 years
    assert year_used == 2018
    year_used, profile = un.education_profile(toy, "DDD", 2022)
    assert year_used is None and profile.empty
    assert un.education_profile(toy, "ZZZ", 2022)[0] is None


def test_education_years_lists_only_years_with_education_data(toy):
    assert un.education_years(toy, "AAA") == [2020, 2022]
    assert un.education_years(toy, "BBB") == [2018]
    assert un.education_years(toy, "ZZZ") == []


def test_largest_sorts_both_ways_and_skips_missing():
    frame = pd.DataFrame({"country": list("abcd"), "x": [3.0, np.nan, -2.0, 1.0]})
    assert list(un.largest(frame, "x", 2)["country"]) == ["a", "d"]
    assert list(un.largest(frame, "x", 2, ascending=True)["country"]) == ["c", "d"]
    assert len(un.largest(frame, "x", 10)) == 3


def test_gender_summary_and_median_by_year(toy):
    summary = un.gender_summary(toy, 2022)
    assert summary == {"economies": 3, "female_higher": 1, "male_higher": 1, "median_gap_pp": 0.0}  # gaps: -2, 0, +2
    assert un.median_by_year(toy, "gender_gap").loc[2022] == 0.0
    assert un.median_by_year(toy, "total").loc[2022] == 5.0  # totals 6, 4, 5


def test_trend_filters_countries_and_years(toy):
    out = un.trend(toy, ["AAA", "BBB"], "total", 2019, 2022)
    assert sorted(zip(out["iso3"], out["year"])) == [("AAA", 2020), ("AAA", 2022), ("BBB", 2022)]


def test_cross_section_adds_names(toy):
    cs = un.cross_section(toy, 2022, {"AAA": "Alpha", "BBB": "Beta", "CCC": "Gamma"})
    assert list(cs["country"]) == ["Alpha", "Beta", "Gamma"]


# --- sanity checks against the cached World Bank data -------------------------------------------------


@pytest.fixture(scope="module")
def real():
    return un.load()


def test_real_headline_series_cover_most_economies_and_decades(real):
    table = un.coverage_table(real, un.economy_count()).set_index("indicator")
    for code in ("SL.UEM.TOTL.ZS", "SL.UEM.TOTL.FE.ZS", "SL.UEM.TOTL.MA.ZS", "SL.UEM.1524.ZS"):
        assert table.loc[code, "economies"] >= 180
        assert table.loc[code, "first_year"] <= 1991 and table.loc[code, "last_year"] >= 2024
    assert un.economy_count() >= 200


def test_real_education_series_are_sparse_and_the_app_knows_it(real):
    table = un.coverage_table(real, un.economy_count()).set_index("indicator")
    for code in ("SL.UEM.BASC.ZS", "SL.UEM.INTM.ZS", "SL.UEM.ADVN.ZS"):
        assert table.loc[code, "median_years_per_economy"] < 15  # far fewer years than the headline series' 35
        assert table.loc[code, "economies"] >= 150
    per_year = un.economies_per_year(real, un.EDUCATION)
    assert per_year.loc[2019].min() >= 100 and per_year.loc[2025].max() < 40
    assert un.default_year(real) == 2024


def test_real_usa_2024_matches_the_published_values(real):
    row = real.loc[("USA", 2024)]
    assert (row["female"], row["male"]) == pytest.approx((3.914, 4.112))
    assert row["gender_gap"] == pytest.approx(3.914 - 4.112)
    assert row["youth_ratio"] == pytest.approx(8.920 / 4.022, rel=1e-3)
    assert row["education_gap"] == pytest.approx(6.501 - 2.608)


def test_real_total_always_lies_between_female_and_male_rates(real):
    both = real.dropna(subset=["total", "female", "male"])
    low = both[["female", "male"]].min(axis=1) - 1e-6
    high = both[["female", "male"]].max(axis=1) + 1e-6
    assert ((both["total"] >= low) & (both["total"] <= high)).all()


def test_real_gender_gap_2024(real):
    summary = un.gender_summary(real, 2024)
    assert summary["economies"] >= 175 and summary["female_higher"] > summary["male_higher"]
    cs = un.cross_section(real, 2024, {})
    top = un.largest(cs, "gender_gap", 1).iloc[0]
    assert top["iso3"] == "IRQ" and top["gender_gap"] == pytest.approx(16.6, abs=0.05)


def test_real_education_snapshot_extends_coverage_but_labels_the_year(real):
    exact = un.education_snapshot(real, 2024, max_age=0)
    fallback = un.education_snapshot(real, 2024)
    assert len(exact) >= 80 and len(fallback) > len(exact)
    assert fallback["year_used"].between(2019, 2024).all()
    assert (fallback["year_used"] < 2024).any()
    year_used, profile = un.education_profile(real, "IND", 2024)
    assert year_used == 2024 and profile["advanced"] > profile["basic"]  # in India graduates face the higher rate
