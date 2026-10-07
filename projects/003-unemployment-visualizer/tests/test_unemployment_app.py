"""Smoke tests: the Streamlit app renders with its defaults and after changing the main controls."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120).run()


def test_app_runs_with_defaults():
    at = run_app()
    assert not at.exception
    assert len(at.tabs) == 4 and len(at.metric) == 3


def test_app_every_gap_measure_renders():
    at = run_app()
    for measure in ("gender_gap", "youth_ratio", "education_gap"):
        at.radio[0].set_value(measure).run()
        assert not at.exception


def test_app_year_with_no_education_data_degrades_gracefully():
    at = run_app()
    at.sidebar.slider[1].set_value(1992).run()  # the "Year for comparisons" slider
    assert not at.exception
    at.radio[0].set_value("education_gap").run()
    assert not at.exception


def test_app_without_countries_still_runs():
    at = run_app()
    at.sidebar.multiselect[0].set_value([]).run()
    assert not at.exception
