"""Smoke test: the app runs end to end on the committed data without raising."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_runs_without_exception():
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    assert not at.exception


def test_app_runs_for_euro_area_and_other_bis_economies():
    at = AppTest.from_file(str(APP), default_timeout=90).run()
    at.sidebar.selectbox[0].set_value("XM").run()
    assert not at.exception
    at.sidebar.checkbox[0].check().run()
    assert not at.exception
    for code in ("JP", "BR"):  # Brazil has a 1990 hyperinflation spike that the axis crop must handle
        at.sidebar.selectbox[0].set_value(code).run()
        assert not at.exception
