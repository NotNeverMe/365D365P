"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_with_defaults():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert not at.error


def test_app_per_hour_measure_and_other_window():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.radio[0].set_value("Per hour worked (estimate, to 2023)").run()
    assert not at.exception
    at.sidebar.slider[0].set_range(1995, 2015).run()
    assert not at.exception


def test_app_with_no_countries_shows_a_message_not_a_crash():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.sidebar.multiselect[0].set_value([]).run()
    assert not at.exception
    assert any("at least one country" in i.value for i in at.info)
