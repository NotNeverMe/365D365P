"""Window growth of GDP and GDP per capita for every economy, ready for a world map.

Growth over a window is the compound annual growth rate (CAGR) between the first
and last year, computed from *levels*. It is not the average of annual growth
rates: see ``cagr_vs_mean_annual`` for why the two differ.

All functions are pure and take or return pandas objects; Streamlit lives in ``app.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core import worldbank as wb

CODES = {
    "per_capita": "NY.GDP.PCAP.KD",  # GDP per capita, constant 2015 US$
    "total": "NY.GDP.MKTP.KD",  # GDP, constant 2015 US$
    "annual_pc_growth": "NY.GDP.PCAP.KD.ZG",  # annual % growth of GDP per capita
}
MEASURES = {"per_capita": "GDP per capita", "total": "Total GDP"}


# ------------------------------------------------------------------------------------ loading


def load() -> pd.DataFrame:
    """Wide frame indexed by (iso3, year): per_capita, total, annual_pc_growth. Economies only (no aggregates)."""
    return wb.indicators(CODES)


def economies() -> pd.DataFrame:
    """All World Bank economies that are not aggregates: iso3, name, region, income_group."""
    meta = wb.countries()
    return meta[~meta["is_aggregate"]][["iso3", "name", "region", "income_group"]].reset_index(drop=True)


def level_matrix(wide: pd.DataFrame, column: str) -> pd.DataFrame:
    """Rows = year, columns = iso3."""
    return wide[column].unstack("iso3").sort_index()


# ------------------------------------------------------------------------------------ growth


def window_cagr(levels: pd.DataFrame, start: int, end: int) -> pd.Series:
    """Compound annual growth (%) from ``start`` to ``end`` for each economy.

    ``(level_end / level_start) ** (1 / (end - start)) - 1``. NaN where either end year is missing
    or not positive. Only the two end years matter, so a country with gaps in between still counts.
    """
    if end <= start:
        raise ValueError("end year must be after start year")
    if start not in levels.index or end not in levels.index:
        return pd.Series(np.nan, index=levels.columns, name="cagr_pct")
    a, b = levels.loc[start], levels.loc[end]
    ok = (a > 0) & (b > 0)
    out = ((b[ok] / a[ok]) ** (1.0 / (end - start)) - 1.0) * 100.0
    return out.reindex(levels.columns).rename("cagr_pct")


def mean_annual_growth(annual_growth: pd.DataFrame, start: int, end: int) -> pd.Series:
    """Arithmetic mean (%) of the annual growth rates for years start+1 .. end.

    Needs every one of those years; economies with any year missing get NaN. Shown only to
    compare with the CAGR: the arithmetic mean is biased upward when growth is volatile.
    """
    years = [y for y in range(start + 1, end + 1)]
    window = annual_growth.reindex(years)
    complete = window.notna().all(axis=0)
    return window.mean(axis=0).where(complete).rename("mean_annual_pct")


def cagr_vs_mean_annual(levels: pd.DataFrame, annual_growth: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    """CAGR, arithmetic mean of annual growth, and their difference (mean minus CAGR, pp) for one window."""
    out = pd.concat([window_cagr(levels, start, end), mean_annual_growth(annual_growth, start, end)], axis=1)
    out["mean_minus_cagr_pp"] = out["mean_annual_pct"] - out["cagr_pct"]
    return out.dropna()


def make_windows(first: int, last: int, length: int, *, include_partial: bool = False) -> list[tuple[int, int]]:
    """Consecutive windows of ``length`` years from ``first``: (1960, 1970), (1970, 1980), ...

    A final shorter window ending at ``last`` is added only if ``include_partial`` is true.
    """
    if length <= 0:
        raise ValueError("length must be positive")
    windows = []
    s = first
    while s + length <= last:
        windows.append((s, s + length))
        s += length
    if include_partial and s < last:
        windows.append((s, last))
    return windows


def window_label(window: tuple[int, int]) -> str:
    return f"{window[0]}-{window[1]}"


def window_table(levels: pd.DataFrame, start: int, end: int, meta: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per economy (including those with no data): name, region, income group, levels, CAGR.

    Economies without both end years have NaN growth and stay in the table, so the map can show
    them as missing instead of dropping them.
    """
    meta = economies() if meta is None else meta
    t = meta.set_index("iso3").copy()
    t["start_level"] = levels.loc[start].reindex(t.index) if start in levels.index else np.nan
    t["end_level"] = levels.loc[end].reindex(t.index) if end in levels.index else np.nan
    t["cagr_pct"] = window_cagr(levels, start, end).reindex(t.index)
    return t.reset_index()


def panel(levels: pd.DataFrame, windows: list[tuple[int, int]], meta: pd.DataFrame | None = None) -> pd.DataFrame:
    """Long frame (window, iso3, name, region, cagr_pct) with every economy in every window."""
    meta = economies() if meta is None else meta
    frames = []
    for w in windows:
        t = window_table(levels, w[0], w[1], meta)[["iso3", "name", "region", "cagr_pct"]]
        t.insert(0, "window", window_label(w))
        frames.append(t)
    return pd.concat(frames, ignore_index=True)


# ------------------------------------------------------------------------------------ summaries


def coverage(growth: pd.Series | pd.DataFrame, total_economies: int) -> dict:
    """How many of the economies have a growth rate (``growth`` is the cagr column or Series)."""
    s = growth["cagr_pct"] if isinstance(growth, pd.DataFrame) else growth
    n = int(s.notna().sum())
    return {"with_data": n, "total": total_economies, "share": n / total_economies if total_economies else float("nan")}


def negative_share(growth: pd.Series) -> float:
    """Share of economies with data whose window growth is below zero (NaN if none have data)."""
    g = growth.dropna()
    return float((g < 0).mean()) if len(g) else float("nan")


def window_summary(levels: pd.DataFrame, windows: list[tuple[int, int]], total_economies: int) -> pd.DataFrame:
    """Per window: economies with data, coverage, share with negative growth, median and mean growth."""
    rows = []
    for s, e in windows:
        g = window_cagr(levels, s, e)
        cov = coverage(g, total_economies)
        rows.append(
            {
                "window": window_label((s, e)),
                "with_data": cov["with_data"],
                "coverage": cov["share"],
                "negative_share": negative_share(g),
                "median_cagr_pct": g.median(),
                "mean_cagr_pct": g.mean(),
            }
        )
    return pd.DataFrame(rows)


def top_bottom(table: pd.DataFrame, n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The ``n`` fastest and ``n`` slowest economies by ``cagr_pct`` (those with data only)."""
    t = table.dropna(subset=["cagr_pct"]).sort_values("cagr_pct", ascending=False)
    return t.head(n).reset_index(drop=True), t.tail(n).sort_values("cagr_pct").reset_index(drop=True)


def region_summary(table: pd.DataFrame, by: str = "region") -> pd.DataFrame:
    """Median, first and third quartile and interquartile range of ``cagr_pct`` by group, plus counts.

    Quartiles use linear interpolation (pandas default). ``economies`` is the group size,
    ``with_data`` the number with a growth rate.
    """
    g = table.groupby(by)["cagr_pct"]
    out = pd.DataFrame(
        {
            "economies": g.size(),
            "with_data": g.count(),
            "median": g.median(),
            "q1": g.quantile(0.25),
            "q3": g.quantile(0.75),
        }
    )
    out["iqr"] = out["q3"] - out["q1"]
    return out.sort_values("median", ascending=False)


def color_limit(values: pd.Series | np.ndarray, quantile: float = 0.90, floor: float = 1.0) -> float:
    """Symmetric colour-scale limit: the ``quantile`` of |values|, rounded up to a whole number.

    Computed once over *all* frames of an animation so colours mean the same in every frame.
    """
    v = np.abs(np.asarray(values, dtype=float))
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return floor
    return float(max(floor, np.ceil(np.quantile(v, quantile))))


# ------------------------------------------------------------------------------------ summary


def _p(df: pd.DataFrame, digits: int = 2) -> str:
    return df.to_string(float_format=lambda v: f"{v:,.{digits}f}")


def main() -> None:
    wide = load()
    meta = economies()
    total = len(meta)
    print(f"World Bank economies (non-aggregates): {total}")
    for col in CODES:
        s = wide[col].dropna()
        yrs = s.index.get_level_values("year")
        print(f"{CODES[col]:>20}: {yrs.min()}-{yrs.max()}, {s.index.get_level_values('iso3').nunique()} economies, last year has {s[yrs == yrs.max()].shape[0]}")

    pc = level_matrix(wide, "per_capita")
    tot = level_matrix(wide, "total")
    zg = level_matrix(wide, "annual_pc_growth")
    last = int(pc.index.max())

    decades = make_windows(1960, last, 10, include_partial=True)
    print(f"\n== GDP per capita growth by decade (CAGR %), coverage and share negative ==")
    print(_p(window_summary(pc, decades, total).set_index("window")))
    print(f"\n== Total GDP growth by decade ==")
    print(_p(window_summary(tot, decades, total).set_index("window")))

    # headline window
    s, e = 1990, 2019
    t = window_table(pc, s, e, meta)
    cov = coverage(t, total)
    print(f"\n== Per capita CAGR {s}-{e}: {cov['with_data']} of {total} economies ({cov['share']:.0%}) ==")
    print(f"median {t['cagr_pct'].median():.2f}%, share negative {negative_share(t['cagr_pct']):.1%}")
    top, bottom = top_bottom(t)
    print("top 10:", "; ".join(f"{r['name']} {r['cagr_pct']:.1f}" for _, r in top.iterrows()))
    print("bottom 10:", "; ".join(f"{r['name']} {r['cagr_pct']:.1f}" for _, r in bottom.iterrows()))
    print("\nBy region (median, quartiles, IQR; %/yr):")
    print(_p(region_summary(t)))
    print("\nBy income group:")
    print(_p(region_summary(t, "income_group")))

    # countries without data in the headline window
    missing = t[t["cagr_pct"].isna()]
    print(f"\nNo data for {s}-{e}: {len(missing)} economies, e.g. {', '.join(missing['name'].head(8))}")

    # CAGR vs arithmetic mean
    cmp_ = cagr_vs_mean_annual(pc, zg, s, e)
    print(f"\n== CAGR vs mean of annual growth, per capita {s}-{e}, {len(cmp_)} economies with every year ==")
    d = cmp_["mean_minus_cagr_pp"]
    print(f"mean minus CAGR: median {d.median():.3f} pp, 90th percentile {d.quantile(0.9):.2f} pp, max {d.max():.2f} pp, never negative: {(d >= -1e-9).all()}")
    worst = d.nlargest(3)
    print("largest gaps:", "; ".join(f"{meta.set_index('iso3').loc[i, 'name']} {v:.2f} pp (CAGR {cmp_.loc[i, 'cagr_pct']:.2f}, mean {cmp_.loc[i, 'mean_annual_pct']:.2f})" for i, v in worst.items()))

    # recent window
    t2 = window_table(pc, 2010, 2019, meta)
    t3 = window_table(pc, 2019, last, meta)
    print(f"\nPer capita 2010-2019: median {t2['cagr_pct'].median():.2f}%, negative {negative_share(t2['cagr_pct']):.1%}; "
          f"2019-{last}: median {t3['cagr_pct'].median():.2f}%, negative {negative_share(t3['cagr_pct']):.1%} (n={t3['cagr_pct'].notna().sum()})")

    # total vs per capita
    tt = window_table(tot, s, e, meta)
    both = pd.concat([t.set_index("iso3")["cagr_pct"], tt.set_index("iso3")["cagr_pct"]], axis=1, keys=["pc", "tot"]).dropna()
    print(f"\nTotal vs per capita {s}-{e}: median total {both['tot'].median():.2f}% vs per capita {both['pc'].median():.2f}%; "
          f"countries negative in per capita but positive in total: {((both['pc'] < 0) & (both['tot'] > 0)).sum()}")

    lim = color_limit(panel(pc, decades, meta)["cagr_pct"])
    lim_total = color_limit(panel(tot, decades, meta)["cagr_pct"])
    print(f"\nColour limit for the decade animation (90th percentile of |CAGR|, rounded up): +/-{lim:.0f}% per capita, +/-{lim_total:.0f}% total GDP")


if __name__ == "__main__":
    main()
