"""Streamlit app: what governments spend money on, by function and by economic category."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import charts, ui
from core import worldbank as wb
import gov_spending as gs

ui.page(
    "Government Spending Explorer",
    "What governments spend on (function, % of GDP) and what they spend it on (economic category, % of total expense). "
    "The two views use different denominators and are never added together.",
    icon="🏛️",
)


@st.cache_data
def get_data() -> pd.DataFrame:
    return gs.load()


@st.cache_data
def get_cofog() -> pd.DataFrame:
    return gs.load_cofog()


@st.cache_data
def get_names() -> dict[str, str]:
    return wb.names()


def hbar(frame: pd.DataFrame, y: str, x: str, x_title: str, height: int = 360) -> go.Figure:
    """Horizontal bar chart in the house style (core.charts.bars resets hover mode and height, so set them afterwards)."""
    fig = charts.bars(frame, x=x, y=y, orientation="h", text_auto=".1f")
    fig.update_layout(height=height, hovermode="closest", yaxis=dict(autorange="reversed", title=None), xaxis_title=x_title, showlegend=False)
    return fig


df = get_data()
cofog = get_cofog()
names = get_names()
labels = gs.labels()
interest_year = gs.broad_year(df, "interest")

compare = ui.country_picker(names, default=["USA", "GBR", "DEU", "FRA", "JPN", "BRA", "IND"], label="Countries for the trends view")
first, last = ui.year_range(1972, 2024, (1990, 2024))

tab_country, tab_trend, tab_cross, tab_interest, tab_cov = st.tabs(
    ["Country breakdown", "Trends", "Cross-country", "Interest burden", "Coverage"]
)

# ------------------------------------------------------------------------------ country breakdown
with tab_country:
    c1, c2, c3 = st.columns([2, 1, 1])
    by_name = sorted(names, key=lambda c: names[c])
    iso = c1.selectbox("Country", by_name, index=by_name.index("USA"), format_func=lambda c: names[c])
    year = c2.slider("Year", 1972, 2024, interest_year)
    lag = c3.slider("Use data up to N years older", 0, 5, 3, help="Fills a gap with the latest earlier observation. The year used is shown in the table.")
    snap = gs.snapshot(df, iso, year, max_lag=lag)
    have = snap.dropna(subset=["value"])
    missing = snap[snap["value"].isna()]["indicator"].tolist()

    left, right = st.columns(2)
    with left:
        st.subheader("By function, % of GDP")
        fn = have[have["group"] == "function"]
        if fn.empty:
            st.info("No functional spending series for this country and year.")
        else:
            st.plotly_chart(hbar(fn, "indicator", "value", "% of GDP", 260))
        exp = have[have["key"] == "expense"]
        if len(exp):
            st.caption(f"For context, central government total expense: {exp['value'].iloc[0]:.1f}% of GDP "
                       f"(data for {int(exp['observation_year'].iloc[0])}). Education and health cover general government, "
                       "so these bars cannot be summed or subtracted from that figure.")
    with right:
        as_gdp = st.toggle("Show economic categories as % of GDP instead (share x expense / 100)")
        st.subheader("By economic category, " + ("% of GDP" if as_gdp else "% of total expense"))
        ec = have[have["group"] == "economic"].copy()
        expense = have.loc[have["key"] == "expense", "value"]
        if as_gdp:
            if len(expense):
                ec["value"] = ec["value"] / 100.0 * float(expense.iloc[0])
            else:
                ec = ec.iloc[0:0]
        if ec.empty:
            st.info("No economic-category data for this country and year.")
        else:
            st.plotly_chart(hbar(ec, "indicator", "value", "% of GDP" if as_gdp else "% of total expense", 320))
            if not as_gdp:
                st.caption(f"Reported categories add up to {ec['value'].sum():.1f}% of total expense.")

    if missing:
        st.warning("Not reported for this country within the chosen window: " + ", ".join(missing) + ".")

    if iso in set(cofog["iso3"]):
        st.subheader("Full functional classification (COFOG), general government, Eurostat")
        basis = st.radio("Measure", ["% of GDP", "% of total expenditure"], horizontal=True)
        shot = gs.cofog_snapshot(cofog, iso, year)
        if shot.empty:
            st.info(f"Eurostat has no COFOG data for this country in {year} (coverage {cofog['year'].min()}-{cofog['year'].max()}).")
        else:
            column = "pc_gdp" if basis == "% of GDP" else "pc_total"
            st.plotly_chart(hbar(shot.sort_values(column, ascending=False), "division", column, basis, 420))
            st.caption(f"General government total expenditure {gs.cofog_total(cofog, iso, year):.1f}% of GDP in {year}.")
    else:
        st.caption("The ten-division COFOG breakdown is only available here for 30 European countries (Eurostat).")

    table = snap.assign(value=snap["value"].round(2)).rename(columns={"observation_year": "data year"})
    st.dataframe(table[["indicator", "denominator", "scope", "value", "data year"]], hide_index=True)

# ------------------------------------------------------------------------------------------ trends
with tab_trend:
    key = st.selectbox("Indicator", [s.key for s in gs.SERIES], format_func=lambda k: f"{gs.BY_KEY[k].label} ({gs.BY_KEY[k].denominator})", key="trend_key")
    series = gs.BY_KEY[key]
    if not compare:
        st.info("Pick at least one country in the sidebar.")
    else:
        long = gs.trend(df, [key], compare, first, last)
        if long.empty:
            st.info("None of the selected countries report this indicator in the chosen years.")
        else:
            fig = charts.lines(long, "year", "value", color="country", yaxis_title=series.denominator, markers=True)
            if st.checkbox("Add the cross-country median (the set of countries changes from year to year)"):
                med = gs.median_by_year(df, [key]).loc[first:last, f"{key}_median"]
                fig.add_trace(go.Scatter(x=med.index, y=med.values, name="Median, all reporting countries", line=dict(color="#4b5563", dash="dash")))
            st.plotly_chart(fig)
        absent = [names[c] for c in compare if c not in set(long["iso3"])]
        if absent:
            st.caption("No data in this window for: " + ", ".join(absent) + ".")
        st.caption(f"Scope: {series.scope}.")

# ---------------------------------------------------------------------------------- cross-country
with tab_cross:
    c1, c2, c3 = st.columns(3)
    key = c1.selectbox("Indicator", [s.key for s in gs.SERIES], format_func=lambda k: f"{gs.BY_KEY[k].label} ({gs.BY_KEY[k].denominator})", key="cross_key")
    years = sorted(df[key].dropna().index.get_level_values("year").unique(), reverse=True)
    broad = gs.broad_year(df, key)
    year_x = c2.selectbox("Year", years, index=years.index(broad), key="cross_year")
    n_show = c3.slider("Countries shown", 5, 40, 20)
    side = st.radio("Show", ["Highest", "Lowest"], horizontal=True)
    sec = gs.cross_section(df, key, year_x)
    st.caption(f"{len(sec)} of {len(names)} economies report this in {year_x}; median {sec['value'].median():.1f} {gs.BY_KEY[key].denominator}.")
    shown = sec.head(n_show) if side == "Highest" else sec.tail(n_show).iloc[::-1]
    st.plotly_chart(hbar(shown, "country", "value", gs.BY_KEY[key].denominator, 120 + 22 * len(shown)))

# --------------------------------------------------------------------------------- interest burden
with tab_interest:
    c1, c2 = st.columns(2)
    int_years = sorted(df["interest"].dropna().index.get_level_values("year").unique(), reverse=True)
    year_i = c1.selectbox("Year", int_years, index=int_years.index(interest_year), key="int_year")
    top_n = c2.slider("Countries shown", 5, 30, 15, key="int_top")
    rank = gs.interest_ranking(df, year_i, top_n)
    n_year = int(df["interest"].xs(year_i, level="year").notna().sum())
    st.caption(f"Ranked among the {n_year} countries that report interest payments in {year_i}. "
               "Interest is a share of central government expense, so a country with small total expense can rank high with a small bill relative to GDP.")
    st.plotly_chart(hbar(rank, "country", "interest_share", "Interest payments, % of total expense", 120 + 24 * len(rank)))
    st.dataframe(
        rank.rename(columns={"interest_share": "interest, % of expense", "interest_gdp": "interest, % of GDP (derived)", "expense_gdp": "expense, % of GDP"})
        .round(1)
        .drop(columns="iso3"),
        hide_index=True,
    )

# -------------------------------------------------------------------------------------- coverage
with tab_cov:
    st.markdown("Every series, its denominator and how many economies report it. Gaps are left as gaps; nothing is interpolated.")
    cov = gs.coverage(df).assign(share_of_economies=lambda d: (d["share_of_economies"] * 100).round(0))
    st.dataframe(cov.rename(columns={"share_of_economies": "% of economies ever covered"}), hide_index=True)
    ui.download(df.reset_index(), "government_spending_world_bank.csv")

ui.sources(
    "World Bank WDI: GC.XPN.* (IMF Government Finance Statistics, **central government**), SE.XPD.TOTL.GD.ZS (UNESCO, general government), "
    "SH.XPD.GHED.GD.ZS (WHO Global Health Expenditure, general government), MS.MIL.XPND.GD.ZS (SIPRI).",
    "Eurostat table gov_10a_exp (COFOG, general government S13), 30 European countries only, cached under data/eurostat/.",
    "Function series are % of GDP; economic categories are % of total central government expense. Scope differs by series "
    "(central vs general government), so values from different series are not additive.",
    "There is no open global COFOG source reachable here: outside Europe only education, health and military are available by function.",
)
