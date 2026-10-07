"""Streamlit app for the Economic Growth Heatmap. Widgets and charts only; the analysis lives in growth_heatmap.py."""

import pandas as pd
import plotly.express as px
import streamlit as st

import growth_heatmap as gh
from core import charts, ui

ui.page(
    "Economic Growth Heatmap",
    "Compound annual growth of GDP across the world, for any window or decade. Grey countries have no data.",
    icon="🗺️",
)


@st.cache_data
def load_levels():
    wide = gh.load()
    return {m: gh.level_matrix(wide, m) for m in gh.MEASURES}, gh.economies()


levels_by_measure, meta = load_levels()
total_economies = len(meta)
last_year = int(levels_by_measure["per_capita"].index.max())
first_year = int(levels_by_measure["per_capita"].index.min())
DECADES = gh.make_windows(1960, last_year, 10, include_partial=True)  # the last one is shorter
FIVE_YEAR = gh.make_windows(1960, last_year, 5, include_partial=True)


def windows_for(step: str) -> list[tuple[int, int]]:
    return DECADES if step == "Decade" else FIVE_YEAR


@st.cache_data
def windows_panel(measure: str, step: str):
    wins = windows_for(step)
    return gh.panel(levels_by_measure[measure], wins, meta), [gh.window_label(w) for w in wins]


def growth_map(df: pd.DataFrame, title: str, limit: float, **kwargs):
    """Choropleth with a fixed, symmetric colour scale. NaN countries keep the grey land colour."""
    fig = charts.choropleth(
        df,
        "iso3",
        "cagr_pct",
        title=title,
        hover_name="name",
        hover_data={"iso3": False, "region": True, "cagr_pct": ":.2f"},
        color_continuous_scale="RdBu",
        range_color=(-limit, limit),
        labels={"cagr_pct": "% a year"},
        **kwargs,
    )
    fig.update_geos(showland=True, landcolor="#d1d5db", showcountries=True, countrycolor="#ffffff")
    return fig


# ------------------------------------------------------------------------------------ sidebar

measure_label = st.sidebar.radio("Measure", list(gh.MEASURES.values()))
measure = next(k for k, v in gh.MEASURES.items() if v == measure_label)
levels = levels_by_measure[measure]

mode = st.sidebar.radio("Window", ["Decade preset", "Custom window"])
if mode == "Decade preset":
    labels = [gh.window_label(w) for w in DECADES]
    choice = st.sidebar.select_slider("Decade", options=labels, value=labels[-2])
    start, end = DECADES[labels.index(choice)]
else:
    start, end = ui.year_range(first_year, last_year, (1990, 2019))
step = st.sidebar.radio("Animation steps", ["Decade", "5-year window"])

panel_df, frame_labels = windows_panel(measure, step)
decade_panel, _ = windows_panel(measure, "Decade")
auto_limit = int(gh.color_limit(decade_panel["cagr_pct"]))
limit = st.sidebar.slider(
    "Colour scale limit (± % a year)",
    2,
    15,
    auto_limit,
    help="Fixed for every map and frame so colours are comparable. Values beyond the limit show the end colour; hover for the exact number.",
)

if end <= start:
    st.warning("Choose a window of at least two years.")
    st.stop()

# ------------------------------------------------------------------------------------ the map

table = gh.window_table(levels, start, end, meta)
cov = gh.coverage(table, total_economies)
neg = gh.negative_share(table["cagr_pct"])

c1, c2, c3 = st.columns(3)
c1.metric("Economies with data", f"{cov['with_data']} of {cov['total']}", f"{cov['share']:.0%} coverage", delta_color="off")
c2.metric("Median growth", f"{table['cagr_pct'].median():.2f}% a year")
c3.metric("Shrinking economies", f"{neg:.0%}", help="Share of economies with data whose level was lower at the end of the window.")

st.plotly_chart(growth_map(table, f"{measure_label}: compound annual growth {start}-{end} (%)", limit), width="stretch")
st.caption("Grey = no data for this window (a start or end year is missing in the World Bank series).")

st.subheader(f"Map over time, by {step.lower()}")
st.plotly_chart(
    growth_map(
        panel_df,
        f"{measure_label}: compound annual growth (%), same colour scale in every frame",
        limit,
        animation_frame="window",
        category_orders={"window": frame_labels},
    ),
    width="stretch",
)

# ------------------------------------------------------------------------------------ tables and summaries

top, bottom = gh.top_bottom(table, 10)
show = ["name", "region", "start_level", "end_level", "cagr_pct"]
rename = {"name": "Economy", "region": "Region", "start_level": f"Level {start}", "end_level": f"Level {end}", "cagr_pct": "% a year"}
left, right = st.columns(2)
left.subheader("Fastest 10")
left.dataframe(top[show].rename(columns=rename).round(2), hide_index=True, width="stretch")
right.subheader("Slowest 10")
right.dataframe(bottom[show].rename(columns=rename).round(2), hide_index=True, width="stretch")
st.caption("Small economies (island states, oil exporters) can top or bottom these lists; levels are constant 2015 US$.")

left, right = st.columns(2)
regions = gh.region_summary(table)
box = px.box(table.dropna(subset=["cagr_pct"]), x="region", y="cagr_pct", points="all", hover_name="name")
box.update_xaxes(title_text="", tickangle=-25)
left.plotly_chart(charts.theme(box, title=f"Growth by World Bank region, {start}-{end} (% a year)", yaxis_title="% a year").update_layout(hovermode="closest"), width="stretch")

summary = gh.window_summary(levels, windows_for(step), total_economies)
neg_fig = charts.bars(summary, "window", "negative_share", title=f"Share of economies with negative growth, by {step.lower()}")
neg_fig.update_yaxes(tickformat=".0%", title_text="")
right.plotly_chart(neg_fig, width="stretch")

st.subheader("Region summary: median and interquartile range")
st.dataframe(
    regions.rename(columns={"economies": "Economies", "with_data": "With data", "median": "Median", "q1": "Q1", "q3": "Q3", "iqr": "IQR"}).round(2),
    width="stretch",
)
st.subheader("Coverage and negative share by window")
by_window = summary.assign(coverage=summary["coverage"] * 100, negative_share=summary["negative_share"] * 100).rename(
    columns={
        "window": "Window",
        "with_data": "With data",
        "coverage": "Coverage %",
        "negative_share": "Negative %",
        "median_cagr_pct": "Median % a year",
        "mean_cagr_pct": "Mean % a year",
    }
)
st.dataframe(by_window.round(2), hide_index=True, width="stretch")

ui.download(table.round(4), f"growth_{measure}_{start}_{end}.csv")
ui.sources(
    "World Bank WDI: GDP per capita (NY.GDP.PCAP.KD) and GDP (NY.GDP.MKTP.KD), constant 2015 US$; country regions and income groups from the World Bank country list.",
    "Growth is the compound annual rate between the two end years, not an average of annual rates. Coverage is thinner in early windows (107 of 217 economies have data for 1960-1970).",
    "Limits: constant-price US$ levels are revised by the World Bank and are not PPP-adjusted; windows depend on the end years chosen (business-cycle position); the 2020-2025 window is five years.",
)
