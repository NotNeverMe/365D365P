"""Smoke tests: the Streamlit app renders with its defaults and after changing the main controls."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60).run()


def test_app_runs_with_defaults():
    at = run_app()
    assert not at.exception
    assert len(at.tabs) == 3 and len(at.metric) == 3


def test_app_switches_to_per_capita_and_handles_no_countries():
    at = run_app()
    at.sidebar.radio[0].set_value("GDP per capita").run()
    assert not at.exception
    at.sidebar.multiselect[0].set_value([]).run()
    assert not at.exception
    assert at.info  # prompts the user to pick a country
