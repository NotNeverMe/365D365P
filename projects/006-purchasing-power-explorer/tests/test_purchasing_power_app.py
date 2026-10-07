"""Smoke tests: the Streamlit app runs without exceptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def fresh() -> AppTest:
    return AppTest.from_file(APP).run(timeout=180)


def test_app_runs_with_defaults():
    at = fresh()
    assert not at.exception
    assert not at.error
    assert [t.label for t in at.tabs] == ["Converter", "Over/undervaluation", "Income: nominal vs PPP", "Price level vs income"]
    labels = [m.label for m in at.metric]
    assert "Slope (elasticity)" in labels and "At market exchange rate" in labels


def test_every_valuation_basis_renders():
    at = fresh()
    for basis in ["Big Mac, GDP-adjusted index", "World Bank price level (PPP / exchange rate)", "Big Mac, raw index"]:
        at.radio(key="pp_basis").set_value(basis).run(timeout=60)
        assert not at.exception


def test_nominal_income_regression_and_old_year():
    at = fresh()
    at.radio(key="pp_income").set_value("gdp_nominal").run(timeout=60)
    assert not at.exception
    assert any("overstates" in w.value for w in at.warning)
    at.select_slider(key="pp_year").set_value(1995).run(timeout=60)  # no Big Mac overlap in 1995
    assert not at.exception


def test_converter_country_change():
    at = fresh()
    at.selectbox(key="pp_country").set_value("CHE").run(timeout=60)
    assert not at.exception
    assert any("buys locally" in m.label for m in at.metric)
