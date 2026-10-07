"""Smoke test: the app runs end to end on the committed data without raising."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_runs_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception


def test_app_runs_with_other_choices():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.sidebar.multiselect[0].set_value(["IND", "SGP"]).run()  # different economies, still plots
    assert not at.exception
    for box in at.selectbox:  # partner tab: a reporter whose data ends early
        if box.label == "Reporter":
            box.set_value("RUS").run()
    assert not at.exception
