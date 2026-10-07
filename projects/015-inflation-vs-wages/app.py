"""Streamlit app for Inflation vs Wages. Widgets and charts only; the analysis lives in inflation_wages.py."""

import calendar

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import inflation_wages as iw
from core import charts, ui
from core import worldbank as wb

ui.page(
    "Inflation vs Wages",
    "Have US wages kept pace with consumer prices? Real wages, episodes where prices outran pay, and a cross-country check.",
    icon="💵",
)


@st.cache_data
def load_us():
    return iw.load_us()


@st.cache_data
def load_panel():
    us_cpi = iw.load_us()["cpi"].dropna()
    return iw.load_panel_wages(), iw.panel_inflation(us_cpi)


us = load_us()
cpi = us["cpi"].dropna()

# ------------------------------------------------------------------------------------ sidebar

wage_id = st.sidebar.selectbox("Wage series", list(iw.WAGE_SERIES), format_func=lambda s: iw.WAGE_SERIES[s])
df = iw.aligned(us[wage_id], cpi)
ppy = iw.periods_per_year(df.index)
first_year, last_year = int(df.index.year.min()), int(df.index.year.max())

start_year, end_year = ui.year_range(first_year, last_year, (first_year, last_year))
base_year = st.sidebar.slider("Base year for the real-wage index", first_year, last_year, max(first_year, min(2019, last_year)))
base_month = st.sidebar.selectbox("Base month", range(1, 13), format_func=lambda m: calendar.month_name[m])
min_periods = st.sidebar.slider(
    "Shortest episode to list (periods)", 1, 24, 6, help="Months for monthly series, quarters for the quarterly median series."
)

window = df.loc[f"{start_year}-01-01":f"{end_year}-12-31"]
base = pd.Timestamp(year=base_year, month=base_month, day=1)
if len(window) < 2 * ppy:
    st.warning("Choose a window of at least two years.")
    st.stop()
if base > window.index.max():
    st.warning("The base month is after the last observation in the window.")
    st.stop()
if base < window.index.min():
    base = window.index.min()
    st.caption(f"Base month is before the window; using {base:%B %Y}.")

# ------------------------------------------------------------------------------------ headline numbers

real = iw.real_wage(window)
cum = iw.cumulative_real_change(real, base)
r12 = iw.real_growth(window, "12m")
episodes = iw.gap_episodes(window, min_periods)

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Real wage since {cum.index[0]:%b %Y}", f"{cum.iloc[-1]:+.1f}%", f"to {cum.index[-1]:%b %Y}", delta_color="off")
c2.metric("Periods with falling real wages", f"{iw.negative_share(r12):.0%}", help="Share of periods whose 12-month real wage growth was below zero.")
c3.metric("Episodes of prices outrunning wages", len(episodes), help=f"Runs of at least {min_periods} periods with 12-month inflation above 12-month wage growth.")
c4.metric("Latest 12-month real growth", f"{r12.dropna().iloc[-1]:+.2f}%", f"{r12.dropna().index[-1]:%b %Y}", delta_color="off")

# ------------------------------------------------------------------------------------ charts

rebased = window.loc[cum.index[0] :]
index_df = pd.DataFrame(
    {
        "Nominal wage": rebased["wage"] / rebased["wage"].iloc[0] * 100,
        "Consumer prices (CPI-U)": rebased["cpi"] / rebased["cpi"].iloc[0] * 100,
        "Real wage": (real.loc[cum.index[0] :] / real.loc[cum.index[0]]) * 100,
    }
).reset_index().melt("date", var_name="series", value_name="index")
left, right = st.columns(2)
left.plotly_chart(
    charts.lines(index_df, "date", "index", "series", title=f"Wages and prices, {cum.index[0]:%b %Y} = 100", yaxis_title="Index"),
    width="stretch",
)

rates = pd.DataFrame(
    {"Inflation": iw.growth(window["cpi"], "12m", ppy), "Wage growth": iw.growth(window["wage"], "12m", ppy)}
).dropna()
rates_fig = charts.lines(rates.reset_index().melt("date", var_name="series", value_name="pct"), "date", "pct", "series", title="12-month inflation and wage growth (%)", yaxis_title="%")
for _, e in episodes.iterrows():
    rates_fig.add_vrect(x0=e["start"], x1=e["end"], fillcolor="#dc2626", opacity=0.10, line_width=0)
right.plotly_chart(rates_fig, width="stretch")
right.caption("Shaded: runs in which 12-month inflation exceeded 12-month wage growth.")

left, right = st.columns(2)
annual = iw.annual_table(window)
annual_fig = go.Figure(
    go.Bar(
        x=annual.index,
        y=annual["gap_pp"],
        marker_color=["#dc2626" if g > 0 else "#2563eb" for g in annual["gap_pp"]],
        hovertemplate="%{x}: %{y:+.1f} pp<extra></extra>",
    )
)
annual_fig.add_hline(y=0, line_color="#4b5563")
left.plotly_chart(
    charts.theme(annual_fig, title="Calendar years: inflation minus wage growth (pp; red = prices outran wages)", yaxis_title="pp").update_layout(hovermode="closest"),
    width="stretch",
)

kind = right.selectbox("Cross-correlation on", ["12m", "3m", "1m", "12m_diff"], format_func=lambda k: iw.GROWTH_KINDS[k])
max_lag = right.slider("Maximum lag (periods)", 6, 48, 24)
try:
    cc = iw.cross_correlation(iw.growth(window["cpi"], kind, ppy), iw.growth(window["wage"], kind, ppy), max_lag)
    pk = iw.peak_lag(cc)
    colors = ["#dc2626" if lag == pk["lag"] else "#2563eb" for lag in cc.index]
    cc_fig = go.Figure(go.Bar(x=cc.index, y=cc.values, marker_color=colors, hovertemplate="lag %{x}: r = %{y:.2f}<extra></extra>"))
    unit = "months" if ppy == 12 else "quarters"
    cc_fig.update_xaxes(title_text=f"Lag k in {unit} (positive: wage growth follows inflation)")
    right.plotly_chart(charts.theme(cc_fig, title="Cross-correlation of wage growth with inflation", yaxis_title="correlation", height=380).update_layout(hovermode="closest"), width="stretch")
    right.caption(
        f"Highest correlation {pk['correlation']:.2f} at lag {pk['lag']:+d} {unit} (lag 0: {pk['lag0']:.2f}); "
        f"within 0.02 of the peak from lag {pk['plateau'][0]:+d} to {pk['plateau'][1]:+d}. "
        "Persistent series give broad, unstable peaks, and correlation is not causation."
    )
except ValueError as err:
    right.info(str(err))

# ------------------------------------------------------------------------------------ tables

st.subheader("Episodes in which prices outran wages")
if len(episodes):
    show = episodes.assign(
        start=episodes["start"].dt.strftime("%Y-%m"), end=episodes["end"].dt.strftime("%Y-%m"), peak_date=episodes["peak_date"].dt.strftime("%Y-%m")
    ).rename(
        columns={
            "start": "Start", "end": "End", "periods": "Periods", "mean_gap_pp": "Mean gap (pp)", "peak_gap_pp": "Peak gap (pp)",
            "peak_date": "Peak at", "inflation_at_peak": "Inflation at peak (%)", "wage_growth_at_peak": "Wage growth at peak (%)",
        }
    )  # fmt: skip
    st.dataframe(show.round(2), hide_index=True, width="stretch")
else:
    st.info("No episodes of at least that length in this window.")

st.subheader("Decades")
decades = iw.decade_summary(window)
st.dataframe(
    decades.assign(**{"from": decades["from"].dt.strftime("%Y-%m"), "to": decades["to"].dt.strftime("%Y-%m"), "share_falling_real_wage": decades["share_falling_real_wage"] * 100})
    .rename(
        columns={
            "decade": "Decade", "from": "From", "to": "To", "years": "Years", "inflation_pct": "Inflation (% a yr)",
            "wage_growth_pct": "Wage growth (% a yr)", "real_wage_growth_pct": "Real wage growth (% a yr)", "share_falling_real_wage": "Periods with falling real wage (%)",
        }
    )
    .round(2),
    hide_index=True,
    width="stretch",
)
st.caption("Compound annual rates between the first and last observation of each decade. A decade starts at the last observation of the previous one.")

out = pd.DataFrame({"wage": window["wage"], "cpi": window["cpi"], "real_wage": real, "real_growth_12m_pct": r12}).reset_index()
ui.download(out, f"real_wage_{wage_id}.csv")

# ------------------------------------------------------------------------------------ cross-country panel

st.divider()
st.subheader("Other countries: real hourly earnings in manufacturing")
wages, inflation = load_panel()
names = wb.names()
p1, p2 = st.columns(2)
panel_base = p1.slider("Panel base year", 2005, 2023, 2019)
panel_last = p2.slider("Panel last year", 2020, 2025, 2025)
if panel_last <= panel_base:
    st.warning("The last year must be after the base year.")
else:
    status = iw.panel_status(wages, inflation, panel_base, panel_last)
    panel = iw.panel_real_wages(wages, inflation, status, panel_base, panel_last)
    summary = iw.panel_summary(panel)
    included = list(summary.index)
    pick = st.multiselect("Countries", included, default=[c for c in ["USA", "GBR", "DEU", "FRA", "JPN", "KOR", "MEX", "POL"] if c in included], format_func=lambda c: names.get(c, c))
    shown = panel[panel["iso3"].isin(pick)].assign(country=lambda d: d["iso3"].map(names))
    base_rows = pd.DataFrame({"iso3": pick, "year": panel_base, "cumulative_real_pct": 0.0, "country": [names.get(c, c) for c in pick]})
    line = pd.concat([base_rows, shown[["iso3", "year", "cumulative_real_pct", "country"]]])
    st.plotly_chart(
        charts.lines(line, "year", "cumulative_real_pct", "country", title=f"Real hourly earnings in manufacturing since {panel_base} (% change)", yaxis_title="%"),
        width="stretch",
    )
    st.caption(
        f"{int(status['included'].sum())} of {len(status)} candidate countries have complete data from {panel_base} to {panel_last}; "
        f"in {int((summary['cumulative_real_pct'] > 0).sum())} of them real earnings are higher in {panel_last}."
    )
    dropped = status[~status["included"]].assign(country=lambda d: [names.get(i, i) for i in d.index])[["country", "wage_series", "reason"]]
    with st.expander(f"Dropped countries ({len(dropped)}) and why"):
        st.dataframe(dropped, hide_index=True, width="stretch")

ui.sources(
    "FRED: CPIAUCSL (CPI-U); AHETPI, CES0500000003 (average hourly earnings); LEU0252881500Q (median usual weekly earnings, quarterly, deflated here by the quarter's average CPI, mean gap from BLS's own real series 0.6%).",
    "Panel: OECD hourly earnings in manufacturing via FRED (LCEAMN01<ISO2>...661), deflated by World Bank CPI inflation (FP.CPI.TOTL.ZG; the US from CPI-U). The OECD's own CPI series on FRED end in 2025 or earlier.",
    "The BLS did not publish a CPI for October 2025, so the US series has a one-month hole; growth rates are computed on calendar dates and the cross-correlation uses the longest unbroken stretch.",
    "Limits: wages versus CPI is not a living-standards measure: average earnings change with the mix of jobs (composition), exclude benefits, and CPI-U has its own measurement issues.",
)
