"""Streamlit app: exchange-rate volatility, instability periods, worst episodes, ranking and correlations."""

import math

import pandas as pd
import plotly.express as px
import streamlit as st
from plotly.subplots import make_subplots

from core import charts, ui
from fx_volatility import (
    CURRENCIES,
    episode_table,
    format_table,
    instability_cutoff,
    instability_flag,
    instability_periods,
    instability_summary,
    load_rates,
    rebased,
    return_correlation,
    rolling_vol,
    volatility_ranking,
)

ui.page(
    "Currency volatility analyzer",
    "Exchange rates against the US dollar: how volatile, when unstable, how far they fell, and how currencies move together.",
    icon="💱",
)

SHADE = "#dc2626"


@st.cache_data
def rates_all() -> pd.DataFrame:
    return load_rates()


@st.cache_data
def vol_all(window: int) -> pd.DataFrame:
    return rolling_vol(rates_all(), window)


rates = rates_all()
names = {code: cur.name for code, cur in CURRENCIES.items()}

# ------------------------------------------------------------------ sidebar
chosen = ui.country_picker(names, ["EUR", "JPY", "GBP", "MXN", "BRL"], key="currencies", label="Currencies")
last_year = int(rates.index[-1].year)
start_year, end_year = ui.year_range(1971, last_year, (2000, last_year))
window = st.sidebar.select_slider("Volatility window (trading days)", options=[10, 21, 30, 63, 126, 252], value=30)
method = st.sidebar.radio(
    "Instability flag",
    ["relative", "absolute"],
    format_func={"relative": "Relative: above the currency's own percentile", "absolute": "Absolute: above a fixed volatility"}.get,
)
if method == "relative":
    threshold = st.sidebar.slider("Percentile of own rolling volatility", 0.50, 0.99, 0.90, 0.01)
else:
    threshold = st.sidebar.slider("Annualised volatility above (%)", 3.0, 40.0, 15.0, 0.5)
merge_days = st.sidebar.slider("Merge unstable runs closer than (days)", 0, 90, 30, 5)
horizon = st.sidebar.radio("Depreciation horizon (days)", [30, 90], horizontal=True)

if not chosen:
    st.info("Pick at least one currency in the sidebar.")
    st.stop()

lo, hi = f"{start_year}-01-01", f"{end_year}-12-31"
vol = vol_all(window)
tab_rates, tab_vol, tab_episodes, tab_cross = st.tabs(
    ["Rates", "Volatility and instability", "Worst episodes", "Ranking and correlation"]
)

# ------------------------------------------------------------------ rates
with tab_rates:
    view = st.radio("Show", ["Rebased index (100 at start)", "Exchange rate (USD per unit)"], horizontal=True)
    if view.startswith("Rebased"):
        idx = rebased(rates[chosen], lo, hi)
        if idx.empty:
            st.info("The chosen currencies have no common dates in this range.")
        else:
            long = idx.reset_index().melt(id_vars="date", var_name="currency", value_name="index")
            fig = charts.lines(long, "date", "index", color="currency", title=f"Value of one unit in US dollars, {idx.index[0]:%Y-%m-%d} = 100")
            fig.add_hline(y=100, line_width=1, line_color="#9ca3af")
            st.plotly_chart(fig)
            st.caption("Starts at the first date every chosen currency has a rate. Above 100 = stronger than at the start, below = weaker.")
    else:
        n_cols = 2 if len(chosen) > 1 else 1
        n_rows = math.ceil(len(chosen) / n_cols)
        fig = make_subplots(rows=n_rows, cols=n_cols, shared_xaxes=False, subplot_titles=[names[c] for c in chosen], vertical_spacing=min(0.1, 0.5 / max(n_rows - 1, 1)))
        for i, code in enumerate(chosen):
            s = rates[code].dropna().loc[lo:hi]
            fig.add_scatter(x=s.index, y=s.values, name=code, showlegend=False, line=dict(color=charts.PALETTE[i % len(charts.PALETTE)], width=1.4), row=i // n_cols + 1, col=i % n_cols + 1)
        charts.theme(fig, title="US dollars per one unit of foreign currency (falling = depreciation)", height=max(320, 260 * n_rows))
        st.plotly_chart(fig)

# ------------------------------------------------------------------ volatility
with tab_vol:
    focus = st.selectbox("Currency to inspect", chosen, format_func=lambda c: names[c])
    v_full = vol[focus].dropna()
    cutoff = instability_cutoff(v_full, method, threshold)
    flag = instability_flag(vol[focus], cutoff)
    periods = instability_periods(flag, vol[focus], merge_days)
    shown = periods[(periods["end"] >= lo) & (periods["start"] <= hi)]
    s = rates[focus].dropna().loc[lo:hi]
    v = vol[focus].loc[lo:hi]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.45, 0.55])
    fig.add_scatter(x=s.index, y=s.values, name=f"{focus}, USD per unit", line=dict(color=charts.PALETTE[0], width=1.4), row=1, col=1)
    fig.add_scatter(x=v.index, y=v.values, name=f"{window}-day volatility", line=dict(color=charts.PALETTE[3], width=1.4), row=2, col=1)
    fig.add_hline(y=cutoff, line_dash="dash", line_color=SHADE, annotation_text=f"cut-off {cutoff:.1f}%", annotation_position="top left", row=2, col=1)
    for _, p in shown.iterrows():
        fig.add_vrect(x0=max(p["start"], pd.Timestamp(lo)), x1=min(p["end"], pd.Timestamp(hi)), fillcolor=SHADE, opacity=0.13, line_width=0)
    fig.update_yaxes(title_text="USD per unit", row=1, col=1)
    fig.update_yaxes(title_text="annualised, %", row=2, col=1)
    charts.theme(fig, title=f"{names[focus]}: rate, rolling volatility and unstable periods (shaded)", height=640)
    st.plotly_chart(fig)
    share = float(flag[vol[focus].notna()].mean())
    rule = f"own {threshold:.0%} percentile of rolling volatility" if method == "relative" else f"fixed level {threshold:.1f}%"
    st.caption(
        f"A day is unstable when {window}-day annualised volatility is above {cutoff:.2f}% ({rule}, computed over the currency's whole history). "
        f"That flags {share:.1%} of its days. Volatility measures the size of moves in either direction."
    )

    st.subheader(f"Unstable periods for {names[focus]} in the selected years")
    st.dataframe(format_table(shown.sort_values("days", ascending=False)), hide_index=True)

    st.subheader("Rolling volatility of all chosen currencies")
    vv = vol[chosen].loc[lo:hi].reset_index().melt(id_vars="date", var_name="currency", value_name="volatility").dropna()
    st.plotly_chart(charts.lines(vv, "date", "volatility", color="currency", yaxis_title="annualised, %"))

    st.subheader("Instability summary (whole history of each series)")
    summary = instability_summary(rates[chosen], window=window, method=method, threshold=threshold, merge_days=merge_days)
    st.dataframe(format_table(summary, 3), hide_index=True)

# ------------------------------------------------------------------ episodes
with tab_episodes:
    sliced = rates[chosen].loc[lo:hi]
    eps = episode_table(sliced, horizons=(30, 90), n=1)
    fig = px.bar(eps.assign(horizon=eps["horizon_days"].astype(str) + "-day"), x="currency", y="change_pct", color="horizon", barmode="group")
    fig.update_layout(hovermode="closest")
    charts.theme(fig, title=f"Worst depreciation against the dollar, {start_year}-{end_year}", yaxis_title="change in USD value, %", height=380)
    st.plotly_chart(fig)

    st.subheader(f"Top {horizon}-day depreciation episodes")
    per_currency = st.slider("Episodes per currency", 1, 5, 3)
    top = episode_table(sliced, horizons=(horizon,), n=per_currency).drop(columns=["horizon_days"])
    st.dataframe(format_table(top, 4), hide_index=True)
    st.caption("Non-overlapping windows. Change = end rate / start rate - 1 in USD per foreign unit, so -20% means the currency lost a fifth of its dollar value.")

# ------------------------------------------------------------------ cross-currency
with tab_cross:
    ranking = volatility_ranking(rates, lo, hi)
    fig = px.bar(ranking.sort_values("vol_pct"), x="vol_pct", y="currency", orientation="h")
    fig.update_layout(hovermode="closest")
    charts.theme(fig, title=f"Annualised volatility of daily returns, {start_year}-{end_year} (all 12 currencies)", height=420)
    fig.update_xaxes(title_text="annualised volatility, %")
    st.plotly_chart(fig)
    st.dataframe(format_table(ranking), hide_index=True)
    st.caption("Each currency is measured over the years selected, from its own first observation if later (euro from 1999, Brazil from 1995, Mexico from late 1993).")

    st.subheader("Correlation of returns")
    freq = st.radio("Return frequency", ["W", "D"], format_func={"W": "Weekly", "D": "Daily"}.get, horizontal=True)
    if len(chosen) < 2:
        st.info("Pick at least two currencies to see correlations.")
    else:
        corr = return_correlation(rates[chosen], freq, lo, hi)
        fig = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r", aspect="auto")
        fig.update_layout(hovermode="closest")
        charts.theme(fig, title=f"Correlation of {'weekly' if freq == 'W' else 'daily'} log returns against the dollar", height=460)
        st.plotly_chart(fig)
        st.caption("Returns are in USD per foreign unit, so a common dollar move pushes all correlations up. Weekly returns reduce time-zone and holiday mismatches.")

# ------------------------------------------------------------------ footer
export = pd.concat({"rate_usd_per_unit": rates[chosen], f"volatility_{window}d_pct": vol[chosen]}, axis=1).loc[lo:hi]
export.columns = [f"{a}_{b}" for a, b in export.columns]
ui.download(export.reset_index(), "fx_rates_volatility.csv", label="Download rates and volatility (CSV)")
ui.sources(
    "Exchange rates: FRED, Federal Reserve H.10 daily series DEXUSEU, DEXJPUS, DEXUSUK, DEXINUS, DEXCHUS, DEXCAUS, DEXSZUS, DEXBZUS, DEXMXUS, DEXKOUS, DEXSFUS, DEXTHUS (noon buying rates in New York).",
    "All rates are converted to US dollars per one foreign unit. Instability is a statistical flag on volatility, not a judgement about policy; "
    "managed currencies (yuan, rupee, baht before 1997) show discrete official adjustments as jumps. Associations with historical events are not causal tests.",
)
