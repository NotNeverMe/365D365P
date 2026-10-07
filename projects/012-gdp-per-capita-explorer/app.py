"""Streamlit app: compare living standards using GDP per capita and related indicators."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import charts, ui
from core import worldbank as wb
import gdp_per_capita as gp

ui.page(
    "GDP per Capita Explorer",
    "Income against life expectancy (the Preston curve), a cross-country comparison table, a convergence test, and how unequal the world's average incomes are.",
    icon="🌍",
)


@st.cache_data
def get_data() -> pd.DataFrame:
    return gp.load()


@st.cache_data
def get_names() -> dict[str, str]:
    return wb.names()


df = get_data()
names = get_names()
last_year = gp.latest_common_year(df, ["ppp", "life_exp", "pop"])
table_year_default = gp.latest_common_year(df, gp.TABLE_COLUMNS)
income_years = sorted(int(y) for y in df["ppp"].dropna().index.get_level_values("year").unique())

picked = ui.country_picker(names, default=["USA", "CHN", "IND", "GBR", "DEU", "JPN", "BRA", "NGA"], label="Countries for the comparison table")

tab_preston, tab_table, tab_conv, tab_gini = st.tabs(["Preston curve", "Country comparison", "Convergence", "Inequality between countries"])

# ---------------------------------------------------------------------------------- Preston curve
with tab_preston:
    c1, c2 = st.columns([3, 1])
    year = c1.slider("Year", income_years[0], last_year, last_year, key="preston_year")
    curvature = c2.checkbox("Allow curvature", help="Adds ln(income) squared to the fitted curve.")
    sub = gp.preston_frame(df, year)
    fit = gp.fit_preston(df, year, curvature=curvature)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Slope b (years per log point)", f"{fit.coef('ln_income'):.2f}", help=f"Robust standard error {fit.se('ln_income'):.2f}")
    m2.metric("Intercept a", f"{fit.coef('const'):.2f}", help=f"Robust standard error {fit.se('const'):.2f}")
    m3.metric("R-squared", f"{fit.r2:.3f}")
    m4.metric("Countries", f"{fit.n}")
    text = f"Life expectancy = {fit.coef('const'):.2f} + {fit.coef('ln_income'):.2f} x ln(income)"
    if curvature:
        text += f" + {fit.coef('ln_income_sq'):.3f} x ln(income)^2 (p = {fit.p('ln_income_sq'):.2f})"
    st.caption(f"{text}. Standard error of the slope {fit.se('ln_income'):.2f}. "
               f"In the log-linear form, doubling income goes with {fit.coef('ln_income') * math.log(2):.1f} more years of life expectancy. This is an association, not a causal effect.")

    ppp_all = df["ppp"].dropna()
    life_all = df.loc[df["ppp"].notna() & df["life_exp"].notna(), "life_exp"]
    fig = px.scatter(sub, x="ppp", y="life_exp", size="pop", color="region", hover_name="country", log_x=True, size_max=48,
                     labels={"ppp": "GDP per capita, PPP (constant 2021 intl $, log scale)", "life_exp": "Life expectancy at birth (years)", "region": "Region", "pop": "Population"})
    grid = np.geomspace(sub["ppp"].min(), sub["ppp"].max(), 120)
    fig.add_trace(go.Scatter(x=grid, y=gp.preston_curve(fit, grid), mode="lines", name="Fitted curve", line=dict(color="#111827", width=3), hoverinfo="skip"))
    charts.theme(fig, height=540)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(range=[math.log10(ppp_all.min() * 0.9), math.log10(ppp_all.max() * 1.1)])
    fig.update_yaxes(range=[life_all.min() - 2, life_all.max() + 2])
    st.plotly_chart(fig)

    st.subheader("The fitted slope over time")
    over = gp.preston_over_time(df, income_years[0], last_year)
    band = go.Figure()
    band.add_trace(go.Scatter(x=over["year"], y=over["slope"] + 1.96 * over["slope_se"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    band.add_trace(go.Scatter(x=over["year"], y=over["slope"] - 1.96 * over["slope_se"], fill="tonexty", fillcolor="rgba(37,99,235,0.15)", line=dict(width=0), name="95% interval"))
    band.add_trace(go.Scatter(x=over["year"], y=over["slope"], name="Slope b", line=dict(color=charts.PALETTE[0])))
    charts.theme(band, yaxis_title="Years of life expectancy per log point of income", height=360)
    st.plotly_chart(band)

# ----------------------------------------------------------------------------- country comparison
with tab_table:
    year_t = st.selectbox("Year", sorted(income_years, reverse=True), index=sorted(income_years, reverse=True).index(table_year_default), key="table_year")
    if not picked:
        st.info("Pick at least one country in the sidebar.")
    else:
        raw = gp.comparison_table(df, picked, year_t)
        shown = raw.assign(pop=raw["pop"] / 1e6).rename(
            columns={"ppp": "GDP pc, PPP (2021 intl $)", "nominal": "GDP pc (current US$)", "life_exp": "Life expectancy (years)", "infant_mort": "Infant mortality (per 1,000)",
                     "pop": "Population (millions)", "co2_pc": "CO2 (t CO2e per person)", "electricity": "Electricity (kWh per person)"}
        )
        st.dataframe(shown.drop(columns="iso3").round(1), hide_index=True)
        gaps = int(raw[gp.TABLE_COLUMNS].isna().sum().sum())
        st.caption(f"{gaps} blank cells mean the source reports no value for that country and year; nothing is filled in. "
                   f"Electricity data end before {income_years[-1]} for most countries.")
        ui.download(raw, f"gdp_per_capita_comparison_{year_t}.csv")
    with st.expander("Coverage of every series"):
        st.dataframe(gp.coverage(df), hide_index=True)

# ---------------------------------------------------------------------------------- convergence
with tab_conv:
    c1, c2, c3 = st.columns([3, 1, 1])
    start, end = c1.slider("Window", income_years[0], last_year, (income_years[0], last_year), key="window")
    min_pop = c2.selectbox("Smallest country", [0, 1_000_000, 5_000_000, 10_000_000], format_func=lambda v: "All" if v == 0 else f"{v // 1_000_000}m+ people")
    weighted = c3.checkbox("Weight by population")
    if end - start < 5:
        st.info("Choose a window of at least five years.")
    else:
        reg, sample = gp.beta_convergence(df, start, end, min_pop, weighted)
        beta, se = reg.coef("ln_initial"), reg.se("ln_initial")
        speed = gp.convergence_speed(beta, end - start)
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("beta (pp per year per log point)", f"{beta:.3f}")
        m2.metric("Standard error", f"{se:.3f}")
        m3.metric("p-value", f"{reg.p('ln_initial'):.4f}")
        m4.metric("Countries", f"{reg.n}")
        m5.metric("Half-life of the gap", f"{speed[1]:.0f} years" if speed else "none")
        verdict = "negative: poorer countries grew faster, which is convergence" if beta < 0 else "positive: richer countries grew faster, which is divergence"
        st.caption(f"The coefficient is {verdict}. A country starting with half the income of another grew about {abs(beta) * math.log(2):.2f} "
                   f"percentage points per year {'faster' if beta < 0 else 'slower'} on average. R-squared {reg.r2:.3f}; robust standard errors.")
        fig = px.scatter(sample, x="initial_income", y="growth", size="population", color="region", hover_name="country", log_x=True, size_max=40,
                         labels={"initial_income": f"GDP per capita in {start} (PPP, constant 2021 intl $, log scale)", "growth": f"Average annual growth {start}-{end} (%)", "region": "Region"})
        grid = np.geomspace(sample["initial_income"].min(), sample["initial_income"].max(), 100)
        fig.add_trace(go.Scatter(x=grid, y=reg.coef("const") + beta * np.log(grid), mode="lines", name="Fitted line", line=dict(color="#111827", width=3), hoverinfo="skip"))
        charts.theme(fig, height=520)
        fig.update_layout(hovermode="closest")
        st.plotly_chart(fig)
        st.subheader("The same test over sub-periods")
        windows = [(w[0], w[1]) for w in [(1990, 2000), (2000, 2010), (2010, last_year)] if w[0] >= income_years[0]]
        table = gp.convergence_by_window(df, windows, min_pop, weighted)
        st.dataframe(table.rename(columns={"beta": "beta", "se": "standard error", "p_value": "p-value", "r2": "R-squared", "n": "countries"}).round(3), hide_index=True)

# ---------------------------------------------------------------------------------------- Gini
with tab_gini:
    leave_out = st.multiselect("Leave out", sorted(names, key=lambda c: names[c]), format_func=lambda c: names[c], default=[],
                               help="Recompute the Gini without these countries, for example China, to see how much of the change they explain.")
    g = gp.weighted_gini_by_year(df, leave_out)
    long = g.melt(id_vars="year", value_vars=["gini_weighted", "gini_unweighted"], var_name="measure", value_name="gini")
    long["measure"] = long["measure"].map({"gini_weighted": "Weighted by population (people)", "gini_unweighted": "Unweighted (each country counts once)"})
    st.plotly_chart(charts.lines(long, "year", "gini", color="measure", yaxis_title="Gini coefficient of GDP per capita (PPP)"))
    first_row, last_row = g.set_index("year").loc[g["year"].min()], g.set_index("year").loc[g["year"].max()]
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Weighted Gini, {int(g['year'].min())}", f"{first_row['gini_weighted']:.3f}")
    c2.metric(f"Weighted Gini, {int(g['year'].max())}", f"{last_row['gini_weighted']:.3f}", delta=f"{last_row['gini_weighted'] - first_row['gini_weighted']:+.3f}", delta_color="off")
    c3.metric("Population covered", f"{g['pop_share_covered'].min():.0%} to {g['pop_share_covered'].max():.0%}")
    st.caption("Each person is given their country's average income, so this measures inequality between countries only; inequality within countries is ignored. "
               "Countries with no income figure in a year are left out of that year, and the population covered is shown above.")

ui.sources(
    "World Bank WDI: NY.GDP.PCAP.PP.KD, NY.GDP.PCAP.CD, SP.DYN.LE00.IN, SP.DYN.IMRT.IN, SP.POP.TOTL, EN.GHG.CO2.PC.CE.AR5 (EDGAR), EG.USE.ELEC.KH.PC (IEA).",
    "PPP income starts in 1990 and covers about 199 economies; the older CO2 series EN.ATM.CO2E.PC has been archived by the World Bank, so the EDGAR series is used.",
    "The Preston fit and the convergence test are cross-country associations with one observation per country (or population weights where stated), not causal estimates.",
    "Absolute convergence ignores differences in institutions, education and policy; conditional convergence is not tested here.",
)
