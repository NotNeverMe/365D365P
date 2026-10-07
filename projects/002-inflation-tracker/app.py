"""Streamlit front end for the inflation tracker. All calculations live in inflation_tracker.py."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import inflation_tracker as it
from core import charts, ui
from core import worldbank as wb

ui.page("Inflation tracker", "Which parts of the US consumer basket drive inflation, and how does US inflation compare with other countries?", icon="🧾")


@st.cache_data
def us_data(breakdown: str):
    levels = it.load_levels(breakdown)
    weights = it.estimate_weights(levels)
    return levels, weights, it.contributions(levels, weights)


@st.cache_data
def world_data():
    return it.load_world_inflation()


@st.cache_data
def country_names() -> dict[str, str]:
    return wb.names()


# ---------------------------------------------------------------------------- sidebar controls
st.sidebar.subheader("US CPI categories")
breakdown = st.sidebar.radio("Breakdown", list(it.BREAKDOWNS), help="Each option splits the whole index into non-overlapping categories.")
levels, weights, parts = us_data(breakdown)
cats = it.categories(levels)
rates = it.yoy(levels)

chart_from = st.sidebar.slider("Chart from year", parts.index.min().year, parts.index.max().year - 1, 2015)
month = st.sidebar.select_slider(
    "Month to break down",
    options=list(parts.index),
    value=parts.index.max(),
    format_func=lambda d: d.strftime("%b %Y"),
)

st.sidebar.divider()
st.sidebar.subheader("Countries")
wide = world_data()
names = country_names()
cov = it.world_coverage(wide)
countries = ui.country_picker({iso: names.get(iso, iso) for iso in wide.columns}, key="countries")
start, end = ui.year_range(cov["first_year"], cov["last_year"], (2000, cov["last_year"]), key="years")

colors = dict(zip(cats, px.colors.qualitative.Safe))
colors[it.RESIDUAL] = "#d1d5db"

tab_us, tab_world = st.tabs(["US CPI by category", "Countries compared"])

# ---------------------------------------------------------------------------- tab 1: US categories
with tab_us:
    table = it.month_table(levels, weights, month)
    headline = rates.loc[month, it.HEADLINE]
    top = table.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric(f"All-items inflation, {month:%b %Y}", f"{headline:.2f}%", help="12-month change in the not-seasonally-adjusted CPI-U.")
    m2.metric("Largest contributor", top["category"], f"{top['contribution_pp']:.2f} pp of {headline:.2f}", delta_color="off")
    m3.metric("Unexplained by estimated weights", f"{table.iloc[-1]['contribution_pp']:+.2f} pp", help="The Residual: headline minus the sum of category contributions.")

    since = f"{chart_from}-01-01"
    view = rates.loc[since:]
    st.subheader("Year-on-year inflation")
    fig = go.Figure()
    for cat in cats:
        fig.add_scatter(x=view.index, y=view[cat], name=cat, mode="lines", visible="legendonly", line=dict(color=colors[cat], width=1.5))
    fig.add_scatter(x=view.index, y=view[it.HEADLINE], name=it.HEADLINE, mode="lines", line=dict(color="#111827", width=3))
    fig.add_hline(y=0, line_dash="dot", line_color="#4b5563")
    st.plotly_chart(charts.theme(fig, yaxis_title="12-month change (%)"), width="stretch")
    st.caption("Click a category in the legend to add its own inflation rate to the chart.")

    st.subheader("Contribution of each category (percentage points)")
    window = parts.loc[since:]
    fig = go.Figure()
    for cat in cats + [it.RESIDUAL]:
        fig.add_bar(x=window.index, y=window[cat], name=cat, marker=dict(color=colors[cat], line=dict(width=0)))
    fig.add_scatter(x=window.index, y=rates.loc[window.index, it.HEADLINE], name="All items (headline)", mode="lines", line=dict(color="#111827", width=2))
    fig.update_layout(barmode="relative", bargap=0)
    st.plotly_chart(charts.theme(fig, yaxis_title="Percentage points of inflation"), width="stretch")
    st.caption("Bars add up to the black line. Contributions use ESTIMATED category weights (see below), not the official BLS weights.")

    st.subheader(f"Top contributors, {month:%B %Y}")
    left, right = st.columns([3, 2])
    with left:
        shown = table.dropna(subset=["yoy_pct"])
        fig = px.bar(shown.sort_values("contribution_pp"), x="contribution_pp", y="category", orientation="h", labels={"contribution_pp": "Contribution (pp)", "category": ""})
        fig.update_traces(marker_color="#2563eb")
        fig.update_layout(hovermode="closest")
        st.plotly_chart(charts.theme(fig, height=380), width="stretch")
    with right:
        st.dataframe(
            table.rename(
                columns={
                    "category": "Category",
                    "weight_pct": "Est. weight (%)",
                    "yoy_pct": "12-month change (%)",
                    "contribution_pp": "Contribution (pp)",
                    "share_of_headline_pct": "Share of headline (%)",
                }
            ).round(2),
            hide_index=True,
            width="stretch",
        )
        st.caption(f"Weights are those estimated for {month - pd.DateOffset(months=12):%b %Y}, the base month of the 12-month change.")

    with st.expander("How the weights are estimated, and how well they fit"):
        fit = it.fit_summary(parts, weights)
        st.markdown(
            "The BLS publishes official category weights (relative importance), but bls.gov refused this tool's requests "
            "(HTTP 403), so they are **estimated** here: for every month, a non-negative least-squares regression of the "
            "monthly all-items log change on the monthly log changes of the categories, over the previous "
            f"{it.WINDOW} months. Contribution = estimated weight twelve months earlier x the category's 12-month change."
        )
        st.write(
            f"Across {fit['months']} months the residual averages {fit['mean_abs_residual_pp']:.2f} pp (largest {fit['max_abs_residual_pp']:.2f} pp), "
            f"and the unconstrained weights sum to between {fit['weight_sum_min']:.2f} and {fit['weight_sum_max']:.2f}."
        )
        w = weights.dropna() * 100
        fig = px.line(w.reset_index().melt("index", var_name="category", value_name="weight"), x="index", y="weight", color="category", color_discrete_map=colors, labels={"index": "", "weight": "Estimated weight (%)"})
        st.plotly_chart(charts.theme(fig, yaxis_title="Estimated weight (%)"), width="stretch")

    export = parts.copy()
    export.insert(0, "headline_yoy_pct", rates.loc[parts.index, it.HEADLINE])
    ui.download(export.rename_axis("month").reset_index(), "cpi_category_contributions.csv", label="Download contributions (CSV)")

# ---------------------------------------------------------------------------- tab 2: countries
with tab_world:
    if not countries:
        st.info("Pick at least one country in the sidebar.")
    elif end <= start:
        st.info("Pick a window of at least two years.")
    else:
        above, reporting = it.count_above(wide, end, 10)
        c1, c2 = st.columns(2)
        c1.metric(f"Economies above 10% inflation in {end}", f"{above} of {reporting}", help="Among economies that report a value for that year.")
        c2.metric("Economies with data", cov["economies"], f"{cov['first_year']}-{cov['last_year']}", delta_color="off")

        long = wide.loc[start:end, countries].stack().rename("inflation").reset_index().rename(columns={"iso3": "country"})
        long["country"] = long["country"].map(names)
        capped = st.checkbox("Zoom y-axis to -5% to 30% (hyperinflations dwarf everything else)", value=True)
        fig = charts.lines(long, "year", "inflation", "country", markers=True, yaxis_title="Consumer-price inflation (annual %)")
        fig.add_hline(y=0, line_dash="dot", line_color="#4b5563")
        if capped:
            fig.update_yaxes(range=[-5, 30])
        st.plotly_chart(fig, width="stretch")

        summary = it.country_summary(wide, countries, start, end, names).drop(columns="iso3")
        summary = summary.rename(
            columns={
                "country": "Country",
                "mean_pct": "Average (%)",
                "median_pct": "Median (%)",
                "peak_pct": "Peak (%)",
                "peak_year": "Peak year",
                "latest_pct": "Latest (%)",
                "latest_year": "Latest year",
                "years_with_data": "Years with data",
                "years_expected": "Years expected",
            }
        )
        year_format = st.column_config.NumberColumn(format="%d")
        st.dataframe(summary.round(1), hide_index=True, width="stretch", column_config={"Peak year": year_format, "Latest year": year_format})
        ui.download(summary, f"inflation_{start}_{end}.csv")

ui.sources(
    "US: FRED / BLS CPI-U, not seasonally adjusted, 12-month changes (all-items CPIAUCNS plus the category series listed in the README). The October 2025 index was not published and is left blank.",
    "Category weights are ESTIMATED from the data (rolling non-negative least squares); the official BLS relative-importance table was not reachable (HTTP 403). Each estimate uses the previous five years, so it lags true changes in weights.",
    "Countries: World Bank FP.CPI.TOTL.ZG (consumer prices, annual %, IMF International Financial Statistics). National CPI baskets and methods differ, so levels are only roughly comparable.",
)
