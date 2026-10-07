"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_with_defaults():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 3
    assert len(at.get("plotly_chart")) == 4  # map, animated map, region box plot, negative-share bars


def test_app_total_gdp_custom_window_and_five_year_frames():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.radio[0].set_value("Total GDP").run()
    at.sidebar.radio[1].set_value("Custom window").run()
    at.sidebar.radio[2].set_value("5-year window").run()
    assert not at.exception
    assert not at.error


def test_app_window_too_short_shows_warning_not_crash():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.radio[1].set_value("Custom window").run()
    at.sidebar.slider[0].set_range(2000, 2000).run()
    assert not at.exception
    assert any("at least two years" in w.value for w in at.warning)
