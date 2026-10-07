"""Streamlit app for the Gini Calculator. Widgets and charts only; the analysis lives in gini_calc.py."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import gini_calc as gc
from core import charts, ui
from core import inequality as ineq

ui.page(
    "Gini Calculator",
    "Measure income inequality from your own numbers, then see how countries compare in World Bank survey data.",
    icon="📐",
)


@st.cache_data
def load_table():
    return gc.worldbank_table()


def lorenz_figure(curves: list[tuple[str, np.ndarray, np.ndarray]], title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect equality", line=dict(color="#9ca3af", dash="dash"))
    for name, pop, inc in curves:
        if len(pop) > 600:  # plotting every point of a large sample adds nothing visible
            keep = np.linspace(0, len(pop) - 1, 600).astype(int)
            pop, inc = pop[keep], inc[keep]
        fig.add_scatter(x=pop, y=inc, mode="lines", name=name)
    fig.update_xaxes(title_text="Cumulative share of population (poorest first)", range=[0, 1])
    fig.update_yaxes(title_text="Cumulative share of income", range=[0, 1], scaleanchor="x", scaleratio=1)
    fig = charts.theme(fig, title=title, height=520)
    fig.update_layout(hovermode="closest")
    return fig


# ------------------------------------------------------------------------------------ tab 1


def read_dataset() -> tuple[gc.Dataset, float | None, str]:
    """Collect input from the widgets. Returns the data, a theoretical Gini if known, and a label."""
    source = st.radio("Where do the numbers come from?", ["Example", "Paste numbers", "Upload CSV"], horizontal=True)
    if source == "Example":
        kind = st.selectbox("Example", ["Lognormal", "Pareto", *gc.PRESET_TEXT])
        if kind in ("Lognormal", "Pareto"):
            left, right = st.columns(2)
            n = left.slider("Sample size", 100, 20_000, 2_000, step=100)
            if kind == "Lognormal":
                sigma = right.slider("sigma (spread of log income)", 0.2, 2.0, 0.8, step=0.05)
                data = gc.validate(gc.lognormal_sample(n, sigma))
                return data, gc.lognormal_gini(sigma), f"Lognormal, sigma = {sigma}"
            alpha = right.slider("alpha (tail exponent; lower = fatter top)", 1.2, 5.0, 2.5, step=0.1)
            data = gc.validate(gc.pareto_sample(n, alpha))
            return data, gc.pareto_gini(alpha), f"Pareto, alpha = {alpha}"
        return gc.parse_numbers(gc.PRESET_TEXT[kind]), None, kind
    if source == "Paste numbers":
        text = st.text_area(
            "Incomes, separated by spaces, commas or new lines (no thousands separators)",
            value=gc.PRESET_TEXT["Five households"],
            height=140,
        )
        return gc.parse_numbers(text), None, "Pasted data"
    upload = st.file_uploader("CSV with a column of incomes and, optionally, a weights column", type=["csv", "txt"])
    left, right = st.columns(2)
    value_column = left.text_input("Income column (optional, otherwise detected)") or None
    weight_column = right.text_input("Weights column (optional, otherwise 'weight')") or None
    if upload is None:
        raise gc.InputError("Upload a CSV file to begin.")
    data = gc.parse_csv(upload.getvalue(), value_column, weight_column)
    used = f"column '{data.value_column}'" + (f", weights '{data.weight_column}'" if data.weight_column else ", unweighted")
    return data, None, f"Uploaded CSV ({used})"


def your_data_tab() -> None:
    try:
        data, theory, label = read_dataset()
    except gc.InputError as err:
        st.error(str(err))
        return

    level = st.session_state.get("ci_level", 0.95)
    summary = gc.summarise(
        data.values, data.weights, n_boot=st.session_state.get("n_boot", 500), level=level, seed=st.session_state.get("seed", 0)
    )
    est = summary.gini

    a, b, c, d = st.columns(4)
    a.metric("Gini coefficient", f"{est.gini:.3f}", help="0 = everyone has the same income, 1 = one person has everything.")
    b.metric(f"{level:.0%} bootstrap interval", f"{est.low:.3f} to {est.high:.3f}", help=f"{est.n_boot} resamples, seed {st.session_state.get('seed', 0)}.")
    c.metric("Top 10% income share", f"{summary.top10:.1%}")
    d.metric("Palma ratio", f"{summary.palma:.2f}", help="Income share of the top 10% divided by that of the bottom 40%.")
    note = f"{label}: {summary.n:,} observations" + (" (weighted)" if data.weights is not None else "") + "."
    if theory is not None:
        note += f" Theoretical Gini of this distribution: {theory:.3f}."
    st.caption(note)

    left, right = st.columns([3, 2])
    pop, inc = ineq.lorenz_curve(data.values, data.weights)
    left.plotly_chart(lorenz_figure([(f"Lorenz curve (Gini {est.gini:.3f})", pop, inc)], "Lorenz curve"), width="stretch")
    with right:
        shares = summary.table()
        fig = charts.bars(shares, x="Group", y="Share of income", title="Income share by quintile")
        fig.update_yaxes(tickformat=".0%")
        fig.update_xaxes(title_text="")
        st.plotly_chart(fig, width="stretch")
        st.markdown(
            f"Rebuilt from these five shares alone, the Gini would be **{summary.grouped_gini:.3f}**, "
            f"which is {est.gini - summary.grouped_gini:.3f} below the full-data value. Grouped data hide inequality inside each group."
        )
    ui.download(shares.round({"Share of income": 4}), "quintile_shares.csv", label="Download quintile shares (CSV)")


# ------------------------------------------------------------------------------------ tab 2


def countries_tab(table, picked: list[str], years: tuple[int, int]) -> None:
    latest = gc.latest_per_country(table)
    stats = gc.understatement_summary(latest)
    st.markdown(
        f"Latest survey Gini for **{len(latest)} countries**. Rebuilding the Gini from the five quintile shares alone "
        f"understates the published value by **{stats['mean_gap']:.1f} points on average** "
        f"(range {stats['min_gap']:.1f} to {stats['max_gap']:.1f}); the gap is larger where inequality is higher."
    )

    fig = charts.choropleth(latest, "iso3", "gini_published", title="Published Gini, latest survey year (0-100)", hover_name="country", hover_data={"year": True, "iso3": False}, color_continuous_scale="YlOrRd")
    st.plotly_chart(fig, width="stretch")

    if not picked:
        st.info("Pick one or more countries in the sidebar.")
    else:
        left, right = st.columns(2)
        curves = []
        for iso3 in picked:
            pop, inc, year = gc.lorenz_for_country(table, iso3)
            name = table.loc[table["iso3"] == iso3, "country"].iloc[0]
            curves.append((f"{name} ({year})", pop, inc))
        left.plotly_chart(lorenz_figure(curves, "Lorenz curves rebuilt from quintile shares"), width="stretch")
        trend = table[table["iso3"].isin(picked) & table["year"].between(*years)]
        trend_fig = charts.lines(trend, x="year", y="gini_published", color="country", markers=True, title="Published Gini over time", yaxis_title="Gini (0-100)")
        right.plotly_chart(trend_fig, width="stretch")
        right.caption("Points are survey years; surveys are not annual, so lines join gaps of several years.")

    shown = latest[["country", "year", "gini_published", "gini_grouped", "gap"]].rename(
        columns={"country": "Country", "year": "Survey year", "gini_published": "Published Gini", "gini_grouped": "Quintile-only Gini", "gap": "Understatement"}
    )
    st.dataframe(shown.round(2).sort_values("Published Gini", ascending=False), hide_index=True, width="stretch")
    ui.download(shown.round(2), "gini_latest_by_country.csv")


# ------------------------------------------------------------------------------------ layout

table = load_table()
names = dict(zip(table["iso3"], table["country"]))

st.sidebar.header("Your data")
st.sidebar.slider("Bootstrap resamples", 200, 3000, 500, step=100, key="n_boot")
st.sidebar.select_slider("Confidence level", options=[0.80, 0.90, 0.95, 0.99], value=0.95, key="ci_level")
st.sidebar.number_input("Random seed", min_value=0, value=0, step=1, key="seed")
st.sidebar.header("Countries")
picked = ui.country_picker(names, default=["USA", "BRA", "ZAF", "SWE", "IND", "CHN"], key="gini_countries")
years = ui.year_range(int(table["year"].min()), int(table["year"].max()), (1990, int(table["year"].max())), key="gini_years")

tab_data, tab_countries = st.tabs(["Your data", "Countries"])
with tab_data:
    your_data_tab()
with tab_countries:
    countries_tab(table, picked, years)

ui.sources(
    "Survey Gini `SI.POV.GINI` (0-100) and income shares by quintile `SI.DST.FRST.20` ... `SI.DST.05TH.20`: World Bank Poverty and Inequality Platform via the World Bank Indicators API, CC BY 4.0.",
    "Surveys measure income or consumption depending on the country, so Ginis are not strictly comparable across countries, and survey years differ.",
    "The quintile-only Gini joins the five Lorenz points with straight lines, so it is a lower bound that ignores inequality within each quintile.",
)
