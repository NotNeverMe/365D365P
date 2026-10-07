"""Smoke tests: the Streamlit app renders with its defaults and after changing the main controls."""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def run_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120).run()


def test_app_runs_with_defaults():
    at = run_app()
    assert not at.exception
    assert len(at.tabs) == 2 and len(at.metric) >= 5


def test_app_other_breakdowns_and_a_historic_month():
    at = run_app()
    for option in at.sidebar.radio[0].options[1:]:
        at.sidebar.radio[0].set_value(option).run()
        assert not at.exception
    at.sidebar.select_slider[0].set_value(pd.Timestamp("2022-06-01")).run()
    assert not at.exception
    assert any("Jun 2022" in m.label for m in at.metric)


def test_app_handles_no_countries_selected():
    at = run_app()
    at.sidebar.multiselect[0].set_value([]).run()
    assert not at.exception
    assert at.info
