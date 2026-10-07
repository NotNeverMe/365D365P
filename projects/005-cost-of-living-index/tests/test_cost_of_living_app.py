"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_with_defaults():
    at = AppTest.from_file(APP).run(timeout=120)
    assert not at.exception
    assert [t.label for t in at.tabs] == ["US metro areas (city-level)", "Countries (country averages)"]
    assert len(at.metric) == 6  # three per comparison, two comparisons
    assert any("no open city-level price dataset" in i.value for i in at.info)


def test_country_without_big_mac_data_gives_a_warning_not_an_error():
    at = AppTest.from_file(APP).run(timeout=120)
    at.selectbox(key="country_b").set_value("Nigeria").run(timeout=60)
    at.radio(key="country_measure").set_value("bigmac").run(timeout=60)
    assert not at.exception
    assert any("Big Mac" in w.value for w in at.warning)


def test_changing_year_and_component_works():
    at = AppTest.from_file(APP).run(timeout=120)
    at.select_slider(key="metro_year").set_value(2012).run(timeout=60)
    at.radio(key="metro_component").set_value("Housing").run(timeout=60)
    assert not at.exception
