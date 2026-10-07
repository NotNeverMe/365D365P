"""Loader tests run offline: HTTP is stubbed and the cache is redirected to a temp dir."""

import gzip

import pandas as pd
import pytest

from core import fred, worldbank


class FakeResponse:
    def __init__(self, *, json_data=None, text=""):
        self._json, self.text = json_data, text
        self.content = text.encode()

    def json(self):
        return self._json


@pytest.fixture
def wb_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(worldbank, "WORLDBANK_DIR", tmp_path)
    return tmp_path


def _row(iso, name, year, value):
    return {"countryiso3code": iso, "country": {"value": name}, "date": str(year), "value": value}


def test_worldbank_indicator_parses_and_caches(wb_cache, monkeypatch):
    calls = []

    def fake_get(url, params=None, **_):
        calls.append(url)
        rows = [_row("IND", "India", 2020, -5.8), _row("IND", "India", 2021, None), _row("WLD", "World", 2020, -3.0), _row("", "Odd", 2020, 1.0)]
        return FakeResponse(json_data=[{"pages": 1}, rows])

    monkeypatch.setattr(worldbank, "get", fake_get)
    df = worldbank.indicator("X.Y")
    assert list(df.columns) == ["iso3", "country", "year", "value"]
    assert set(df.iso3) == {"IND", "WLD"}  # null value and bad iso dropped
    assert (wb_cache / "X.Y.csv.gz").exists()

    again = worldbank.indicator("X.Y")  # served from cache
    assert len(calls) == 1
    pd.testing.assert_frame_equal(df, again)


def test_worldbank_error_payload_raises(wb_cache, monkeypatch):
    monkeypatch.setattr(worldbank, "get", lambda *a, **k: FakeResponse(json_data=[{"message": [{"value": "bad"}]}]))
    with pytest.raises(worldbank.DataUnavailable):
        worldbank.indicator("NOPE")


def test_worldbank_wide_drops_aggregates(wb_cache, monkeypatch):
    pd.DataFrame(
        {"iso3": ["IND", "WLD"], "name": ["India", "World"], "region": ["South Asia", "Aggregates"], "income_group": ["Lower middle income", "Aggregates"], "is_aggregate": [False, True]}
    ).to_csv(wb_cache / "_countries.csv", index=False)
    pd.DataFrame({"iso3": ["IND", "WLD"], "country": ["India", "World"], "year": [2020, 2020], "value": [1.0, 2.0]}).to_csv(wb_cache / "A.csv.gz", index=False, compression="gzip")
    wide = worldbank.indicators({"a": "A"})
    assert list(wide.index) == [("IND", 2020)]


def test_fred_parses_missing_values_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(fred, "FRED_DIR", tmp_path)
    csv = "observation_date,FOO\n2020-01-01,1.5\n2020-02-01,.\n2020-03-01,2.5\n"
    monkeypatch.setattr(fred, "get", lambda *a, **k: FakeResponse(text=csv))
    s = fred.series("FOO")
    assert s.index.name == "date" and s.tolist() == [1.5, 2.5]
    monkeypatch.setattr(fred, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should use cache")))
    pd.testing.assert_series_equal(s, fred.series("FOO"), check_freq=False)
    with gzip.open(tmp_path / "FOO.csv.gz") as fh:
        assert fh.readline().decode().strip() == "date,FOO"
