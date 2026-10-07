"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_with_defaults():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4
    assert len(at.get("plotly_chart")) == 5  # index, rates, annual gap, cross-correlation, panel


def test_app_quarterly_median_series_and_later_base():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.selectbox[0].set_value("LEU0252881500Q").run()
    assert not at.exception
    assert not at.error
    at.sidebar.slider[1].set_value(2015).run()  # base year
    at.sidebar.selectbox[1].set_value(6).run()  # base month
    assert not at.exception


def test_app_short_window_warns_instead_of_crashing():
    at = AppTest.from_file(APP, default_timeout=180).run()
    at.sidebar.slider[0].set_range(2000, 2000).run()
    assert not at.exception
    assert any("at least two years" in w.value for w in at.warning)
