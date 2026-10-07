"""Streamlit app: government debt relative to GDP and to revenue."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import charts, ui
from core import worldbank as wb
import national_debt as nd

ui.page(
    "National Debt Dashboard",
    "Central government debt compared with the size of the economy (debt-to-GDP) and with what the government collects (debt-to-revenue).",
    icon="🏦",
)


@st.cache_data
def get_data() -> pd.DataFrame:
    return nd.load()


@st.cache_data
def get_us() -> pd.DataFrame:
    return nd.us_history()


@st.cache_data
def get_names() -> dict[str, str]:
    return wb.names()


def hbar(frame: pd.DataFrame, y: str, x: str, x_title: str, **kwargs) -> go.Figure:
    """Horizontal bars in the house style (core.charts.bars resets hover mode and height, so set them afterwards)."""
    height = 120 + 22 * len(frame)
    fig = charts.bars(frame, x=x, y=y, orientation="h", text_auto=".1f", **kwargs)
    fig.update_layout(height=height, hovermode="closest", yaxis=dict(autorange="reversed", title=None), xaxis_title=x_title, showlegend=False)
    return fig


def excluded_note(measure: str, year: int, lag: int, shown: int) -> None:
    """Say how many countries are missing from a chart and let the reader see which ones and why."""
    out = nd.excluded_countries(df, measure, year, lag)
    with st.expander(f"{shown} countries shown; {len(out)} that report some related data are not shown. Which, and why?"):
        st.dataframe(out.rename(columns={"has_in_window": "has data for", "missing_in_window": "missing"}).drop(columns="iso3"), hide_index=True)


df = get_data()
us = get_us()
names = get_names()

has_debt = sorted(df["debt"].dropna().index.get_level_values("iso3").unique())
picker_names = {c: names[c] for c in has_debt if c in names}
chosen = ui.country_picker(picker_names, default=["USA", "GBR", "CAN", "ESP", "BRA", "MEX", "ZAF", "KOR"], label=f"Countries for trajectories ({len(picker_names)} have debt data)")
first, last = ui.year_range(1990, int(df.index.get_level_values("year").max()), (1990, 2024))

st.sidebar.markdown("---")
years = sorted(df["debt_to_revenue"].dropna().index.get_level_values("year").unique(), reverse=True)
default_year = nd.broad_year(df)
year = st.sidebar.selectbox("Year for rankings and scatter", years, index=years.index(default_year),
                            help="Default is the latest year with at least 75% of the peak number of reporting countries.")
lag = st.sidebar.slider("Use data up to N years older", 0, 5, 0,
                        help="Adds countries whose latest figure is a little older. The year used is shown on hover and in tables.")

tab_traj, tab_rev, tab_int, tab_scatter, tab_us, tab_cov = st.tabs(
    ["Trajectories", "Debt-to-revenue", "Interest burden", "Debt-to-GDP vs debt-to-revenue", "US long history", "Coverage"]
)

with tab_traj:
    measure = st.radio("Measure", ["debt", "debt_to_revenue", "interest_to_revenue"], format_func=lambda m: nd.LABELS[m], horizontal=True)
    if not chosen:
        st.info("Pick at least one country in the sidebar.")
    else:
        traj = nd.trajectories(df, chosen, measure, first, last)
        if traj.empty:
            st.info("None of the selected countries have this measure in the chosen years.")
        else:
            st.plotly_chart(charts.lines(traj, "year", "value", color="country", yaxis_title=nd.LABELS[measure], markers=True))
        absent = [names[c] for c in chosen if c not in set(traj["iso3"])]
        if absent:
            st.caption("No data in this window for: " + ", ".join(absent) + ".")
        st.caption("Lines break where a country has no figure for a year; gaps are not interpolated.")

with tab_rev:
    cols = ["debt_to_revenue", "debt", "revenue"]
    data = nd.latest_complete(df, cols, year, lag).sort_values("debt_to_revenue", ascending=False)
    st.subheader(f"Years of revenue needed to repay central government debt, {year}")
    st.caption("Debt-to-revenue = debt (% of GDP) / revenue excluding grants (% of GDP). A value of 4 means debt equals four years of revenue.")
    fig = hbar(data, "country", "debt_to_revenue", "years of revenue", hover_data={"debt": ":.1f", "revenue": ":.1f", "obs_year": True})
    st.plotly_chart(fig)
    excluded_note("debt_to_revenue", year, lag, len(data))

with tab_int:
    top_n = st.slider("Countries shown", 5, 30, 15)
    burden = nd.interest_burden(df, year, top_n, lag)
    n_int = len(nd.latest_complete(df, ["interest_to_revenue"], year, lag))
    st.subheader(f"Interest payments as % of government revenue, {year}")
    st.caption("Interest / revenue = (interest share of expense x expense % of GDP) / revenue % of GDP. "
               f"Highest {len(burden)} of {n_int} countries with all three inputs.")
    st.plotly_chart(hbar(burden, "country", "interest_to_revenue", "% of revenue", hover_data={"interest_share": ":.1f", "expense": ":.1f", "revenue": ":.1f", "obs_year": True}))
    st.dataframe(
        burden.rename(columns={"interest_to_revenue": "interest, % of revenue", "interest_share": "interest, % of expense", "expense": "expense, % of GDP",
                               "revenue": "revenue, % of GDP", "interest_gdp": "interest, % of GDP", "obs_year": "data year"}).drop(columns="iso3").round(1),
        hide_index=True,
    )
    excluded_note("interest_to_revenue", year, lag, n_int)

with tab_scatter:
    ranks = nd.rank_comparison(df, year, lag)
    st.subheader(f"Two ways to rank the same debt, {year}")
    st.caption(f"{len(ranks)} countries with debt and revenue. Rank correlation (Spearman) between the two orderings: {nd.rank_correlation(ranks):.2f}. "
               "Countries high on the vertical axis owe a lot relative to what their government collects. Countries with similar debt-to-GDP can sit far apart "
               f"because revenue here ranges from {ranks['revenue_gdp'].min():.1f}% to {ranks['revenue_gdp'].max():.1f}% of GDP.")
    log_y = st.checkbox("Log scale for debt-to-revenue", value=False)
    fig = px.scatter(ranks, x="debt_gdp", y="debt_to_revenue", color="income_group", text="iso3", hover_name="country", log_y=log_y,
                     hover_data={"revenue_gdp": ":.1f", "rank_debt_gdp": True, "rank_debt_revenue": True, "obs_year": True, "iso3": False},
                     labels={"debt_gdp": "Debt, % of GDP", "debt_to_revenue": "Debt-to-revenue, years", "income_group": "Income group"})
    fig.update_traces(textposition="top center", textfont_size=10, marker_size=9)
    charts.theme(fig, height=520)
    fig.update_layout(hovermode="closest")
    st.plotly_chart(fig)
    movers = ranks.sort_values("rank_shift", ascending=False)
    st.dataframe(
        movers[["country", "debt_gdp", "revenue_gdp", "debt_to_revenue", "rank_debt_gdp", "rank_debt_revenue", "rank_shift"]]
        .rename(columns={"debt_gdp": "debt, % of GDP", "revenue_gdp": "revenue, % of GDP", "debt_to_revenue": "debt / revenue (years)",
                         "rank_debt_gdp": "rank by debt-to-GDP", "rank_debt_revenue": "rank by debt-to-revenue", "rank_shift": "rank shift (+ = worse on revenue)"})
        .round(1),
        hide_index=True,
    )
    excluded_note("debt_to_revenue", year, lag, len(ranks))

with tab_us:
    st.subheader("US federal debt, % of GDP, quarterly (FRED)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=us.index, y=us["gross"], name="Gross (total public debt)", line=dict(color=charts.PALETTE[0])))
    fig.add_trace(go.Scatter(x=us.index, y=us["held_by_public"], name="Held by the public", line=dict(color=charts.PALETTE[1])))
    if st.checkbox("Overlay the World Bank's US central government debt (annual)"):
        wbus = df["debt"].xs("USA", level="iso3").dropna()
        fig.add_trace(go.Scatter(x=pd.to_datetime(wbus.index.astype(str) + "-07-01"), y=wbus.values, name="World Bank, central government",
                                 mode="markers", marker=dict(color="#16a34a", size=7)))
    charts.theme(fig, yaxis_title="% of GDP", height=480)
    st.plotly_chart(fig)
    ex_g, ex_p = nd.us_extremes(us["gross"]), nd.us_extremes(us["held_by_public"])
    st.caption(f"Gross debt: low {ex_g['min'][1]:.1f}% in {ex_g['min'][0]}, peak {ex_g['max'][1]:.1f}% in {ex_g['max'][0]}, latest {ex_g['latest'][1]:.1f}% in {ex_g['latest'][0]}. "
               f"Held by the public: low {ex_p['min'][1]:.1f}% in {ex_p['min'][0]}, peak {ex_p['max'][1]:.1f}% in {ex_p['max'][0]}, latest {ex_p['latest'][1]:.1f}% in {ex_p['latest'][0]}. "
               "Gross debt includes what the Treasury owes to other parts of the government (for example trust funds).")

with tab_cov:
    cov_year = nd.coverage_by_year(df)
    counts = cov_year[["debt", "revenue", "debt_to_revenue", "interest_to_revenue"]].reset_index().melt(id_vars="year", var_name="measure", value_name="countries")
    counts["measure"] = counts["measure"].map(lambda m: nd.LABELS.get(m, m))
    st.subheader("Countries with data, by year")
    st.plotly_chart(charts.lines(counts, "year", "countries", color="measure", yaxis_title=f"countries (of {len(names)} economies)"))
    st.subheader("Every country that reports any input")
    by_country = nd.coverage_by_country(df)
    st.caption(f"{len(by_country)} economies report at least one input; {int((by_country['debt_years'] == 0).sum())} of them have no debt figure since 1990. "
               "Years are counted from 1990 to the latest year.")
    st.dataframe(by_country.drop(columns="iso3"), hide_index=True)
    ui.download(df.reset_index(), "national_debt_world_bank.csv")

ui.sources(
    "World Bank WDI, from IMF Government Finance Statistics (central government): GC.DOD.TOTL.GD.ZS debt, GC.REV.XGRT.GD.ZS revenue excluding grants, "
    "GC.XPN.INTP.ZS interest (% of expense), GC.XPN.TOTL.GD.ZS expense. Cross-check: GC.XPN.INTP.RV.ZS.",
    "FRED: GFDEGDQ188S (gross federal debt, % of GDP) and FYGFGDQ188S (held by the public), quarterly from 1966 and 1970.",
    "Central government debt is missing for Japan, France, China, Greece and Argentina, and nearly missing for Germany and Italy. Rankings cover only countries that report.",
    "Debt-to-revenue and interest-to-revenue are derived here, not published; every input must be present for the same year.",
)
