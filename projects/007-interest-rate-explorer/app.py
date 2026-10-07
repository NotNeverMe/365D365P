"""Streamlit app: policy rates against inflation and growth, real rates, US Taylor rule and hiking cycles."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core import charts, ui
from interest_rates import (
    AREAS,
    economy_monthly,
    format_table,
    growth_annual,
    hiking_cycles,
    negative_spells,
    policy_rate,
    swing_points,
    taylor_period_summary,
    us_growth_quarterly,
    us_taylor_frame,
)

ui.page(
    "Interest-rate explorer",
    "Central-bank policy rates alongside inflation and economic growth, with real rates, a US Taylor-rule benchmark and US hiking cycles.",
    icon="🏦",
)

BLUE, RED, GREEN, GREY = charts.PALETTE[0], charts.PALETTE[1], charts.PALETTE[2], "#9ca3af"


def axis_range(*series: pd.Series) -> list[float]:
    """Central 98% of the values, padded, so a hyperinflation spike does not flatten the chart."""
    values = pd.concat(series).dropna()
    low, high = values.quantile([0.01, 0.99])
    pad = 0.1 * (high - low)
    return [float(low - pad), float(high + pad)]


def outside(bounds: list[float], *series: pd.Series) -> int:
    values = pd.concat(series).dropna()
    return int(((values < bounds[0]) | (values > bounds[1])).sum())


@st.cache_data
def monthly(area: str, ecb_deposit: bool) -> pd.DataFrame:
    return economy_monthly(area, ecb_deposit=ecb_deposit)


@st.cache_data
def growth(area: str) -> pd.Series:
    return us_growth_quarterly() if area == "US" else growth_annual(area)


@st.cache_data
def taylor(inflation_id: str, r_star: float, pi_star: float) -> pd.DataFrame:
    return us_taylor_frame(r_star=r_star, pi_star=pi_star, inflation_id=inflation_id)


@st.cache_data
def us_rate() -> pd.Series:
    return policy_rate("US")


# ------------------------------------------------------------------ sidebar
area = st.sidebar.selectbox("Economy", list(AREAS), format_func=lambda c: AREAS[c].name, index=0)
ecb_deposit = False
if area == "XM":
    ecb_deposit = st.sidebar.checkbox(
        "Use ECB deposit facility rate (FRED ECBDFR)",
        help="Default is the BIS series: main refinancing rate, deposit rate from Sept 2024.",
    )
data = monthly(area, ecb_deposit)
first_year, last_year = int(data.index[0].year), int(data.index[-1].year)
start, end = ui.year_range(first_year, last_year, (max(first_year, 1980), last_year))
crop = st.sidebar.checkbox("Crop axes to the central 98% of values", value=True, help="Keeps hyperinflation spikes (Brazil 1990, Turkey 2022) from flattening the charts.")
view = data.loc[f"{start}-01-01":f"{end}-12-31"]
name = AREAS[area].name
rate_label = "ECB deposit facility rate" if ecb_deposit else "Policy rate"

tab_rates, tab_real, tab_taylor, tab_cycles = st.tabs(
    ["Rates, inflation, growth", "Real rate", "US Taylor rule", "US hiking cycles"]
)

# ------------------------------------------------------------------ tab 1
with tab_rates:
    g = growth(area)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.62, 0.38])
    fig.add_scatter(x=view.index, y=view["policy_rate"], name=rate_label, line=dict(color=BLUE, width=2), row=1, col=1)
    fig.add_scatter(x=view.index, y=view["inflation"], name="CPI inflation (y/y)", line=dict(color=RED, width=1.6), row=1, col=1)
    if area == "US":
        gv = g.loc[view.index[0] : view.index[-1]]
        fig.add_scatter(x=gv.index, y=gv.values, name="Real GDP growth (y/y, quarterly)", line=dict(color=GREEN, width=1.6), row=2, col=1)
    else:
        gv = g[(g.index >= start) & (g.index <= end)]
        fig.add_bar(
            x=pd.to_datetime(gv.index.astype(str) + "-07-01"), y=gv.values, name="Real GDP growth (annual)",
            marker_color=GREEN, width=1000 * 3600 * 24 * 300, row=2, col=1,
        )
    fig.add_hline(y=0, line_width=1, line_color=GREY, row=1, col=1)
    fig.add_hline(y=0, line_width=1, line_color=GREY, row=2, col=1)
    fig.update_yaxes(title_text="per cent", row=1, col=1)
    fig.update_yaxes(title_text="growth, per cent", row=2, col=1)
    note = ""
    if crop:
        bounds = axis_range(view["policy_rate"], view["inflation"])
        fig.update_yaxes(range=bounds, row=1, col=1)
        if (n_out := outside(bounds, view["policy_rate"], view["inflation"])):
            note = f" The top panel is cropped: {n_out} monthly values lie outside it (untick the sidebar box to see them)."
    charts.theme(fig, title=f"{name}: {rate_label.lower()}, inflation and growth", height=620)
    st.plotly_chart(fig)
    st.caption(
        "Growth is quarterly year-on-year from FRED GDPC1 for the US and annual from the World Bank for other economies." + note
    )

# ------------------------------------------------------------------ tab 2
with tab_real:
    real = view["real_rate"]
    spells = negative_spells(real)
    months_neg = int((real < 0).sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Months in selection", f"{len(real)}")
    c2.metric("Months with negative real rate", f"{months_neg}", f"{months_neg / max(len(real), 1):.0%} of months", delta_color="off")
    c3.metric(f"Latest real rate ({real.index[-1]:%b %Y})", f"{real.iloc[-1]:.2f}%")

    fig = go.Figure()
    for _, spell in spells.iterrows():
        fig.add_vrect(x0=spell["start"], x1=spell["end"] + pd.offsets.MonthEnd(0), fillcolor=RED, opacity=0.12, line_width=0)
    fig.add_scatter(x=real.index, y=real.values, name="Real policy rate", line=dict(color=BLUE, width=2))
    fig.add_hline(y=0, line_width=1, line_color=GREY)
    charts.theme(fig, title=f"{name}: real policy rate (policy rate minus CPI inflation), negative spells shaded", yaxis_title="per cent")
    if crop:
        bounds = axis_range(real)
        fig.update_yaxes(range=bounds)
        if (n_out := outside(bounds, real)):
            st.caption(f"Axis cropped: {n_out} monthly values lie outside it (untick the sidebar box to see them).")
    st.plotly_chart(fig)

    st.subheader("Negative real-rate spells")
    st.dataframe(format_table(spells.sort_values("months", ascending=False)), hide_index=True)

# ------------------------------------------------------------------ tab 3
with tab_taylor:
    st.caption("United States only. Rule: policy rate = r* + inflation + 0.5 (inflation - target) + 0.5 x output gap.")
    c1, c2, c3 = st.columns(3)
    measure = c1.radio("Inflation measure", ["Headline CPI (CPIAUCSL)", "Core CPI (CPILFESL)"], horizontal=False)
    r_star = c2.slider("Neutral real rate r* (%)", 0.0, 4.0, 2.0, 0.25)
    pi_star = c3.slider("Inflation target (%)", 0.0, 4.0, 2.0, 0.25)
    tf = taylor("CPIAUCSL" if measure.startswith("Headline") else "CPILFESL", r_star, pi_star)
    tv = tf.loc[f"{start}-01-01":f"{end}-12-31"]
    if tv.empty:
        st.info("No Taylor-rule quarters in the selected years.")
    else:
        latest = tv.iloc[-1]
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Actual ({tv.index[-1]:%Y} Q{(tv.index[-1].month - 1) // 3 + 1})", f"{latest['actual']:.2f}%")
        m2.metric("Taylor rule", f"{latest['taylor']:.2f}%")
        m3.metric("Actual minus rule", f"{latest['gap_pp']:.2f} pp")
        fig = go.Figure()
        fig.add_scatter(x=tv.index, y=tv["actual"], name="Federal funds rate (quarterly average)", line=dict(color=BLUE, width=2))
        fig.add_scatter(x=tv.index, y=tv["taylor"], name="Taylor rule", line=dict(color=RED, width=2, dash="dash"))
        fig.add_hline(y=0, line_width=1, line_color=GREY)
        charts.theme(fig, title="US federal funds rate against the Taylor rule", yaxis_title="per cent")
        st.plotly_chart(fig)

        periods = {
            "1987-2001": ("1987-01", "2001-12"),
            "2002-2005": ("2002-01", "2005-12"),
            "2009-2015 (zero lower bound)": ("2009-01", "2015-12"),
            "2021-2022": ("2021-01", "2022-12"),
            "2023 onwards": ("2023-01", "2100-01"),
        }
        st.subheader("Average actual minus rule, by period")
        st.dataframe(format_table(taylor_period_summary(tf, periods)), hide_index=True)

# ------------------------------------------------------------------ tab 4
with tab_cycles:
    threshold = st.slider("Minimum swing (percentage points)", 0.5, 4.0, 1.5, 0.25, help="A peak or trough is confirmed once the rate has reversed by this much.")
    rate = us_rate()
    cycles = hiking_cycles(rate, threshold)
    points = swing_points(rate, threshold)
    fig = go.Figure()
    fig.add_scatter(x=rate.index, y=rate.values, name="Federal funds rate", line=dict(color=BLUE, width=1.6))
    peaks, troughs = points[points["kind"] == "peak"], points[points["kind"] == "trough"]
    fig.add_scatter(x=peaks["date"], y=peaks["rate"], mode="markers", name="Peak", marker=dict(color=RED, size=9, symbol="triangle-up"))
    fig.add_scatter(x=troughs["date"], y=troughs["rate"], mode="markers", name="Trough", marker=dict(color=GREEN, size=9, symbol="triangle-down"))
    charts.theme(fig, title="US federal funds rate: turning points", yaxis_title="per cent")
    st.plotly_chart(fig)

    st.subheader("Hiking cycles (trough to peak)")
    st.dataframe(format_table(cycles), hide_index=True)
    st.caption("The last row's cut is still in progress if cut_complete is False.")

# ------------------------------------------------------------------ footer
ui.download(view.reset_index(), f"{area}_rates_inflation.csv", label="Download selected economy (CSV)")
ui.sources(
    "US policy rate, CPI, real GDP and CBO potential GDP: FRED (FEDFUNDS, CPIAUCSL, CPILFESL, GDPC1, GDPPOT).",
    "Other policy rates and CPI inflation: Bank for International Settlements (WS_CBPOL, WS_LONG_CPI). Euro area: ECB deposit rate from FRED ECBDFR on request. Growth: World Bank NY.GDP.MKTP.KD.ZG.",
    "Real rate = policy rate minus year-on-year CPI inflation (ex post, backward looking). Policy rates are monthly averages (US) or end-of-month (BIS). "
    "Potential GDP is today's CBO estimate, not what policymakers saw at the time. Not investment advice.",
)
