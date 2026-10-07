"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_runs_with_defaults():
    at = AppTest.from_file(APP).run(timeout=120)
    assert not at.exception
    assert not at.error
    assert [t.label for t in at.tabs] == ["Your data", "Countries"]
    assert len(at.metric) == 4


def test_app_shows_error_for_bad_pasted_data_and_keeps_running():
    at = AppTest.from_file(APP).run(timeout=120)
    at.radio[0].set_value("Paste numbers").run(timeout=60)
    at.text_area[0].set_value("10 20 abc").run(timeout=60)
    assert not at.exception
    assert any("not a number" in e.value for e in at.error)


def test_app_pareto_example():
    at = AppTest.from_file(APP).run(timeout=120)
    at.selectbox[0].set_value("Pareto").run(timeout=60)
    assert not at.exception
    assert len(at.metric) == 4
