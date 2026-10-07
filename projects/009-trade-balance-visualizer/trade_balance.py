"""Imports, exports, trade balances and trade partners.

Two sources, which measure different things:

* World Bank indicators (via ``core.worldbank``): exports and imports of **goods and services**, in current US$
  and as a share of GDP, for ~200 economies, annual.
* WITS TradeStats (UN Comtrade, via ``wits.worldbank.org``): **merchandise goods only**, by partner, for a
  chosen set of large reporters. Cached under ``data/wits/``.

Never add the two: services are in the first and not in the second.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from core import worldbank
from core.http import DataUnavailable, get
from core.paths import DATA

WITS_DIR = DATA / "wits"
WITS_API = "https://wits.worldbank.org/API/V1"
WITS_FLOWS = {"exports": "XPRT-TRD-VL", "imports": "MPRT-TRD-VL"}  # values in US$ thousand
WORLD = "WLD"  # WITS partner code for the world total

INDICATORS = {
    "exports": "NE.EXP.GNFS.CD",  # exports of goods and services, current US$
    "imports": "NE.IMP.GNFS.CD",
    "net_bop": "BN.GSR.GNFS.CD",  # net trade in goods and services, balance of payments basis
    "exports_gdp": "NE.EXP.GNFS.ZS",
    "imports_gdp": "NE.IMP.GNFS.ZS",
    "openness": "NE.TRD.GNFS.ZS",  # (exports + imports) / GDP, %
    "current_account_gdp": "BN.CAB.XOKA.GD.ZS",
}

# Partner codes that are not countries. UN Comtrade (hence WITS) reports Taiwan as "Other Asia, nes".
UNALLOCATED = {"UNS", "SPE"}  # Unspecified, Special categories
PARTNER_LABELS = {"OAS": "Taiwan (UN label: Other Asia, nes)"}

WITS_REPORTERS = {
    "USA": "United States",
    "CHN": "China",
    "DEU": "Germany",
    "JPN": "Japan",
    "GBR": "United Kingdom",
    "FRA": "France",
    "ITA": "Italy",
    "NLD": "Netherlands",
    "ESP": "Spain",
    "KOR": "South Korea",
    "IND": "India",
    "CAN": "Canada",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "AUS": "Australia",
    "RUS": "Russia",
    "TUR": "Turkey",
    "SAU": "Saudi Arabia",
}


# ------------------------------------------------------------------ World Bank side


def trade_frame(*, refresh: bool = False) -> pd.DataFrame:
    """Annual trade indicators for real economies, indexed by (iso3, year).

    Extra columns: ``balance`` = exports - imports (US$, national-accounts basis), ``balance_gdp`` =
    exports_gdp - imports_gdp (% of GDP), ``implied_gdp`` = exports / (exports_gdp / 100) (US$, used only
    to filter out very small economies).
    """
    wide = worldbank.indicators(INDICATORS, refresh=refresh)
    wide["balance"] = wide["exports"] - wide["imports"]
    wide["balance_gdp"] = wide["exports_gdp"] - wide["imports_gdp"]
    wide["implied_gdp"] = wide["exports"] / (wide["exports_gdp"] / 100.0)
    return wide


def economy(frame: pd.DataFrame, iso3: str) -> pd.DataFrame:
    """One economy's rows, indexed by year."""
    return frame.xs(iso3, level="iso3").sort_index()


def latest_year(frame: pd.DataFrame, column: str = "balance", min_economies: int = 150) -> int:
    """Most recent year in which at least ``min_economies`` economies report ``column``."""
    counts = frame[column].dropna().groupby(level="year").size()
    return int(counts[counts >= min_economies].index.max())


def shading_series(exports: pd.Series, imports: pd.Series) -> pd.DataFrame:
    """Exports and imports with the exact crossing points inserted, for shading surplus against deficit.

    Both inputs are indexed by year. Between two years where the balance changes sign, a row is added at the
    interpolated (fractional) year where the two lines meet. Columns: x, exports, imports.
    """
    pair = pd.concat([exports, imports], axis=1, keys=["exports", "imports"]).dropna().sort_index()
    rows: list[tuple[float, float, float]] = []
    previous = None
    for year, row in pair.iterrows():
        if previous is not None:
            d0, d1 = previous[1] - previous[2], row["exports"] - row["imports"]
            if d0 * d1 < 0:
                t = d0 / (d0 - d1)
                level = previous[1] + t * (row["exports"] - previous[1])
                rows.append((previous[0] + t * (year - previous[0]), level, level))
        rows.append((float(year), float(row["exports"]), float(row["imports"])))
        previous = rows[-1]
    return pd.DataFrame(rows, columns=["x", "exports", "imports"])


def deficit_years(balance: pd.Series) -> dict[str, int]:
    """Years in surplus and in deficit, the longest run of consecutive deficit years, and the last surplus year (0 if none)."""
    b = balance.dropna().sort_index()
    run = longest = 0
    previous = None
    for year, value in b.items():
        if value < 0:
            consecutive = previous is not None and year == previous + 1 and run > 0
            run = run + 1 if consecutive else 1
            longest = max(longest, run)
        else:
            run = 0
        previous = year
    deficit = int((b < 0).sum())
    surplus_years = b.index[b >= 0]
    return {
        "years": len(b),
        "surplus": len(b) - deficit,
        "deficit": deficit,
        "longest_deficit_run": longest,
        "last_surplus_year": int(surplus_years.max()) if len(surplus_years) else 0,
    }


def ranking(
    frame: pd.DataFrame, year: int, by: str = "balance", n: int = 10, *, min_gdp: float = 0.0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Largest surpluses and largest deficits in ``year`` (``by`` = "balance" in US$ or "balance_gdp" in % of GDP).

    ``min_gdp`` (US$) drops economies whose implied GDP is smaller, which keeps tiny economies from
    topping percent-of-GDP rankings. Returns (surpluses, deficits), each with columns
    country, balance, balance_gdp, exports, imports.
    """
    names = worldbank.names()
    rows = frame.xs(year, level="year").dropna(subset=[by, "exports", "imports"])
    rows = rows[rows["implied_gdp"].fillna(0) >= min_gdp].copy()
    rows.insert(0, "country", [names.get(i, i) for i in rows.index])
    cols = ["country", "balance", "balance_gdp", "exports", "imports"]
    rows = rows.sort_values(by)
    return rows.tail(n).iloc[::-1][cols], rows.head(n)[cols]


def coverage(frame: pd.DataFrame, min_economies: int = 150) -> pd.DataFrame:
    """First and last year with data, economy count, and the latest year with at least ``min_economies`` reporting."""
    rows = []
    for col in INDICATORS:
        s = frame[col].dropna()
        years = s.index.get_level_values("year")
        by_year = s.groupby(level="year").size()
        full = by_year[by_year >= min_economies]
        rows.append(
            {
                "indicator": col,
                "code": INDICATORS[col],
                "first_year": int(years.min()),
                "last_year": int(years.max()),
                "economies": int(s.index.get_level_values("iso3").nunique()),
                "latest_full_year": int(full.index.max()) if len(full) else 0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- WITS side


def wits_countries(*, refresh: bool = False) -> pd.DataFrame:
    """WITS country list: iso3, name, is_group. Cached as ``data/wits/_countries.csv``."""
    path = WITS_DIR / "_countries.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, keep_default_na=False)
    root = ET.fromstring(get(f"{WITS_API}/wits/datasource/tradestats-trade/country/ALL", timeout=120).content)
    ns = {"w": "http://wits.worldbank.org"}
    rows = [
        {
            "iso3": c.find("w:iso3Code", ns).text,
            "name": c.find("w:name", ns).text,
            "is_group": c.get("isgroup") == "Yes",
        }
        for c in root.iter("{http://wits.worldbank.org}country")
    ]
    frame = pd.DataFrame(rows)
    WITS_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def parse_wits_json(payload: dict, flow: str) -> pd.DataFrame:
    """SDMX-JSON from the WITS TradeStats endpoint -> tidy (year, flow, partner, value_usd_k)."""
    dims = payload["structure"]["dimensions"]
    partners = [v["id"] for v in next(d for d in dims["series"] if d["id"] == "PARTNER")["values"]]
    partner_pos = [d["id"] for d in dims["series"]].index("PARTNER")
    years = [int(v["id"]) for v in dims["observation"][0]["values"]]
    rows = []
    for key, series in payload["dataSets"][0]["series"].items():
        partner = partners[int(key.split(":")[partner_pos])]
        for t, obs in series["observations"].items():
            if obs[0] is not None:
                rows.append((years[int(t)], flow, partner, float(obs[0])))
    return pd.DataFrame(rows, columns=["year", "flow", "partner", "value_usd_k"])


def _download_partner_trade(reporter: str) -> pd.DataFrame:
    frames = []
    for flow, indicator in WITS_FLOWS.items():
        url = (
            f"SDMX/V21/datasource/tradestats-trade/reporter/{reporter.lower()}/year/all/partner/all/"
            f"product/Total/indicator/{indicator}"
        )
        response = get(f"{WITS_API}/{url}", params={"format": "JSON"}, timeout=180)
        frames.append(parse_wits_json(response.json(), flow))
    frame = pd.concat(frames, ignore_index=True)
    groups = set(wits_countries().query("is_group")["iso3"]) - {WORLD}
    frame = frame[~frame["partner"].isin(groups | {"999"})]  # drop regional aggregates, keep the world total
    frame["value_usd_k"] = frame["value_usd_k"].round(0)  # whole US$ thousand: halves the file, error < US$500
    return frame.sort_values(["flow", "partner", "year"]).reset_index(drop=True)


def partner_trade(reporter: str, *, refresh: bool = False) -> pd.DataFrame:
    """Merchandise exports and imports of ``reporter`` by partner, all years WITS has.

    Columns: year, flow ("exports" / "imports"), partner (ISO-3 or WLD for the world total), value_usd_k
    (US$ thousand). Regional aggregates are removed; the country rows sum to the WLD row. Cached as
    ``data/wits/<REPORTER>.csv.gz``.
    """
    path = WITS_DIR / f"{reporter.upper()}.csv.gz"
    if path.exists() and not refresh:
        return pd.read_csv(path, keep_default_na=False)
    frame = _download_partner_trade(reporter.upper())
    if frame.empty:
        raise DataUnavailable(f"WITS returned no partner data for {reporter}")
    WITS_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, compression="gzip")
    return frame


def partner_names() -> dict[str, str]:
    """ISO-3 (WITS spelling) -> display name for WITS partners."""
    meta = wits_countries()
    return {**dict(zip(meta["iso3"], meta["name"])), **PARTNER_LABELS}


def wits_years(trade: pd.DataFrame) -> list[int]:
    return sorted(int(y) for y in trade["year"].unique())


def top_partners(trade: pd.DataFrame, year: int, flow: str = "exports", n: int = 10) -> pd.DataFrame:
    """Largest partners for one flow and year, with share of the reporter's total and cumulative share.

    Columns: partner, name, value_usd (US$), share (%), cumulative_share (%). The share denominator is the
    WITS world total, so shares of all partners (including unallocated trade) sum to 100.
    """
    sub = trade[(trade["year"] == year) & (trade["flow"] == flow)]
    total = sub.loc[sub["partner"] == WORLD, "value_usd_k"].sum()
    countries = sub[~sub["partner"].isin({WORLD} | UNALLOCATED)].nlargest(n, "value_usd_k")
    out = pd.DataFrame(
        {
            "partner": countries["partner"].to_numpy(),
            "name": [partner_names().get(p, p) for p in countries["partner"]],
            "value_usd": countries["value_usd_k"].to_numpy() * 1000.0,
        }
    )
    out["share"] = out["value_usd"] / (total * 1000.0) * 100.0 if total else np.nan
    out["cumulative_share"] = out["share"].cumsum()
    return out


def bilateral_balance(trade: pd.DataFrame, year: int) -> pd.DataFrame:
    """Merchandise exports, imports and balance with every named partner in ``year`` (US$), by balance.

    Columns: partner, name, exports, imports, balance (exports - imports), total_trade. The balance comes
    entirely from the reporter's own statistics (exports by destination, imports by origin). Unspecified and
    special-category trade is left out, so the rows do not sum to the world balance.
    """
    sub = trade[(trade["year"] == year) & ~trade["partner"].isin({WORLD} | UNALLOCATED)]
    wide = sub.pivot_table(index="partner", columns="flow", values="value_usd_k", aggfunc="sum").fillna(0.0) * 1000.0
    wide = wide.reindex(columns=["exports", "imports"], fill_value=0.0)
    wide["balance"] = wide["exports"] - wide["imports"]
    wide["total_trade"] = wide["exports"] + wide["imports"]
    wide.insert(0, "name", [partner_names().get(p, p) for p in wide.index])
    return wide.sort_values("balance", ascending=False).reset_index()


def world_totals(trade: pd.DataFrame) -> pd.DataFrame:
    """Merchandise exports, imports and balance with the world, by year (US$)."""
    world = trade[trade["partner"] == WORLD].pivot_table(index="year", columns="flow", values="value_usd_k", aggfunc="sum") * 1000.0
    world["balance"] = world["exports"] - world["imports"]
    return world


def concentration(trade: pd.DataFrame, year: int, flow: str = "exports") -> dict[str, float]:
    """Partner concentration among named partners: share of the largest, of the top five, and the Herfindahl index (0-10,000)."""
    sub = trade[(trade["year"] == year) & (trade["flow"] == flow) & ~trade["partner"].isin({WORLD} | UNALLOCATED)]
    total = sub["value_usd_k"].sum()
    shares = (sub["value_usd_k"] / total * 100.0).sort_values(ascending=False)
    return {"top1_share": float(shares.iloc[0]), "top5_share": float(shares.head(5).sum()), "hhi": float((shares**2).sum())}


# ---------------------------------------------------------------------------- main


def format_table(frame: pd.DataFrame, digits: int = 1) -> pd.DataFrame:
    """Display copy: floats rounded."""
    out = frame.copy()
    for col in out.select_dtypes("float").columns:
        out[col] = out[col].round(digits)
    return out


def _bn(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in cols:
        out[col] = out[col] / 1e9
    return out


def main() -> None:
    pd.set_option("display.width", 200, "display.max_columns", 20)
    frame = trade_frame()
    print("== World Bank coverage ==")
    print(coverage(frame).to_string(index=False))

    year = latest_year(frame)
    print(f"\n== Rankings, {year} (exports minus imports of goods and services; US$ bn) ==")
    surplus, deficit = ranking(frame, year, "balance", 8)
    print("Largest surpluses:\n" + format_table(_bn(surplus, ["balance", "exports", "imports"])).to_string(index=False))
    print("Largest deficits:\n" + format_table(_bn(deficit, ["balance", "exports", "imports"])).to_string(index=False))
    surplus, deficit = ranking(frame, year, "balance_gdp", 8, min_gdp=50e9)
    print(f"\n== {year}, balance as % of GDP, economies with GDP above US$50 bn ==")
    print("Largest surpluses:\n" + format_table(_bn(surplus, ["balance", "exports", "imports"])).to_string(index=False))
    print("Largest deficits:\n" + format_table(_bn(deficit, ["balance", "exports", "imports"])).to_string(index=False))

    print("\n== United States, goods and services ==")
    us = economy(frame, "USA")
    print(format_table(_bn(us.loc[[1980, 1990, 2000, 2006, 2010, 2020, year], ["exports", "imports", "balance", "net_bop"]], ["exports", "imports", "balance", "net_bop"]), 0).join(us[["balance_gdp", "openness"]].round(1)).to_string())
    print("Deficit record:", deficit_years(us["balance"]))
    worst = us["balance_gdp"].idxmin()
    print(f"Largest US deficit as % of GDP: {us.loc[worst, 'balance_gdp']:.1f}% in {worst}; {year}: {us.loc[year, 'balance_gdp']:.1f}%")
    _, deficits = ranking(frame, year, "balance", 8)
    print(f"{year} US deficit US${-deficits['balance'].iloc[0] / 1e9:.1f} bn vs the next seven combined US${-deficits['balance'].iloc[1:].sum() / 1e9:.1f} bn")
    print("\n== Deficit record, selected economies (exports minus imports, all years) ==")
    for iso in ["USA", "GBR", "DEU", "CHN", "JPN", "IND"]:
        print(iso, deficit_years(economy(frame, iso)["balance"]), "first year", int(economy(frame, iso)["balance"].dropna().index.min()))

    both = frame.dropna(subset=["balance", "net_bop"]).xs(year, level="year")
    diff = ((both["balance"] - both["net_bop"]).abs() / both["implied_gdp"] * 100).dropna()
    print(f"\nExports minus imports (national accounts) vs net trade (balance of payments), {year}: median gap {diff.median():.2f}% of GDP, 90th percentile {diff.quantile(0.9):.2f}%, n={len(diff)}")
    open_ = frame.xs(year, level="year").query("implied_gdp >= 50e9")["openness"].dropna().sort_values()
    names = worldbank.names()
    print(f"Openness {year}, economies with GDP above US$50 bn: most open " + ", ".join(f"{names[i]} {v:.0f}%" for i, v in open_.tail(3).iloc[::-1].items()) + "; least open " + ", ".join(f"{names[i]} {v:.0f}%" for i, v in open_.head(3).items()))

    print("\n== WITS: merchandise trade by partner (goods only) ==")
    for rep in WITS_REPORTERS:
        t = partner_trade(rep)
        yrs = wits_years(t)
        print(f"{rep}: years {yrs[0]}-{yrs[-1]}, rows {len(t)}")
    usa_wits = world_totals(partner_trade("USA")).loc[2023, "exports"]
    print(f"US 2023: WITS merchandise exports are {usa_wits / us.loc[2023, 'exports']:.1%} of World Bank goods-and-services exports")
    for rep in ["USA", "CHN", "DEU", "CAN"]:
        t = partner_trade(rep)
        y = max(wits_years(t))
        print(f"\n-- {WITS_REPORTERS[rep]} {y}: top export partners")
        print(format_table(top_partners(t, y, "exports", 5).assign(value_usd=lambda d: d["value_usd"] / 1e9), 1).to_string(index=False))
        print(f"   concentration of exports: {concentration(t, y)}")
        bb = bilateral_balance(t, y)
        print("   largest surpluses:", ", ".join(f"{r['name']} {r['balance'] / 1e9:+.1f}bn" for _, r in bb.head(3).iterrows()))
        print("   largest deficits: ", ", ".join(f"{r['name']} {r['balance'] / 1e9:+.1f}bn" for _, r in bb.tail(3).iloc[::-1].iterrows()))
        w = world_totals(t).loc[y]
        print(f"   merchandise: exports {w['exports'] / 1e9:.0f}bn, imports {w['imports'] / 1e9:.0f}bn, balance {w['balance'] / 1e9:+.0f}bn")


if __name__ == "__main__":
    main()
