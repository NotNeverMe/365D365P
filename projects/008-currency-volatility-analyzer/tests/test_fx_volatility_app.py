"""Smoke test: the app runs end to end on the committed data without raising."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_runs_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception


def test_app_runs_with_other_settings():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.radio[0].set_value("absolute").run()  # instability method
    assert not at.exception
    at.sidebar.multiselect[0].set_value(["CNY"]).run()  # one currency: no correlation matrix
    assert not at.exception
    at.sidebar.multiselect[0].set_value(["THB", "KRW", "CHF", "INR"]).run()
    assert not at.exception
