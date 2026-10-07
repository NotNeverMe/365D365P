"""Filesystem locations shared by every project."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORLDBANK_DIR = DATA / "worldbank"
FRED_DIR = DATA / "fred"
BIGMAC_DIR = DATA / "bigmac"
