"""Streamlit app: exports, imports and balances (World Bank), rankings, openness and trade partners (WITS)."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import charts, ui, worldbank
from trade_balance import (
    WITS_REPORTERS,
    bilateral_balance,
    concentration,
    deficit_years,
    economy,
    format_table,
    latest_year,
    partner_trade,
    ranking,
    shading_series,
    top_partners,
    trade_frame,
    wits_years,
    world_totals,
)

ui.page(
    "Trade balance visualizer",
    "Exports, imports and trade balances for ~190 economies, plus who the biggest trading partners are for 18 large ones.",
    icon="🚢",
)

BLUE, ORANGE, GREEN, RED = charts.PALETTE[0], charts.PALETTE[3], "#16a34a", "#dc2626"
GREEN_FILL, RED_FILL = "rgba(22,163,74,0.28)", "rgba(220,38,38,0.28)"


@st.cache_data
def frame() -> pd.DataFrame:
    return trade_frame()


@st.cache_data
def wits(reporter: str) -> pd.DataFrame:
    return partner_trade(reporter)


data = frame()
names = worldbank.names()
available = {iso: names[iso] for iso in data.index.get_level_values("iso3").unique() if iso in names}
last_year = latest_year(data)
newest = int(data.index.get_level_values("year").max())

# ------------------------------------------------------------------ sidebar
chosen = ui.country_picker(available, ["USA", "CHN", "DEU", "JPN", "GBR"], key="economies", label="Economies")
start, end = ui.year_range(1960, newest, (1980, newest))
if newest > last_year:
    st.sidebar.caption(f"Years after {last_year} are partial: fewer than 150 economies have reported.")

if not chosen:
    st.info("Pick at least one economy in the sidebar.")
    st.stop()

tab_balance, tab_open, tab_rank, tab_partners = st.tabs(
    ["Exports, imports, balance", "Openness", "Rankings", "Trade partners (goods only)"]
)

# ------------------------------------------------------------------ balance
with tab_balance:
    focus = st.selectbox("Economy", chosen, format_func=lambda c: names[c])
    view = economy(data, focus).loc[start:end]
    if view[["exports", "imports"]].dropna().empty:
        st.info("No export and import data for this economy in the selected years.")
    else:
        shade = shading_series(view["exports"] / 1e9, view["imports"] / 1e9)
        top = np.maximum(shade["exports"], shade["imports"])
        quiet = dict(line=dict(width=0), hoverinfo="skip", showlegend=False)
        fig = go.Figure()
        fig.add_scatter(x=shade["x"], y=shade["imports"], **quiet)
        fig.add_scatter(x=shade["x"], y=top, fill="tonexty", fillcolor=GREEN_FILL, name="Surplus", line=dict(width=0), hoverinfo="skip")
        fig.add_scatter(x=shade["x"], y=shade["exports"], **quiet)
        fig.add_scatter(x=shade["x"], y=top, fill="tonexty", fillcolor=RED_FILL, name="Deficit", line=dict(width=0), hoverinfo="skip")
        fig.add_scatter(x=view.index, y=view["exports"] / 1e9, name="Exports", line=dict(color=BLUE, width=2))
        fig.add_scatter(x=view.index, y=view["imports"] / 1e9, name="Imports", line=dict(color=ORANGE, width=2))
        charts.theme(fig, title=f"{names[focus]}: exports and imports of goods and services (green = surplus, red = deficit)", yaxis_title="US$ billion, current prices")
        st.plotly_chart(fig)

        bal = view["balance_gdp"].dropna()
        fig = go.Figure()
        fig.add_bar(x=bal.index, y=bal.values, name="Trade balance, % of GDP", marker_color=[GREEN if v >= 0 else RED for v in bal.values])
        ca = view["current_account_gdp"].dropna()
        fig.add_scatter(x=ca.index, y=ca.values, name="Current account, % of GDP", line=dict(color="#374151", width=2, dash="dot"))
        fig.update_layout(hovermode="x unified")
        charts.theme(fig, title=f"{names[focus]}: trade balance and current account as % of GDP", yaxis_title="% of GDP", height=380)
        st.plotly_chart(fig)

        record = deficit_years(economy(data, focus)["balance"])
        st.caption(
            f"Over all years with data ({record['years']}): {record['surplus']} in surplus, {record['deficit']} in deficit; "
            f"longest run of deficit years {record['longest_deficit_run']}"
            + (f"; last surplus year {record['last_surplus_year']}." if record["last_surplus_year"] else ".")
            + " Balance = exports minus imports of goods and services (national accounts); the current account also includes income and transfers."
        )
        table = view.reset_index()[["year", "exports", "imports", "balance", "net_bop", "balance_gdp", "current_account_gdp", "openness"]]
        for col in ["exports", "imports", "balance", "net_bop"]:
            table[col] = table[col] / 1e9
        table = table.rename(columns={"exports": "exports_bn", "imports": "imports_bn", "balance": "balance_bn", "net_bop": "net_trade_bop_bn"})
        st.dataframe(format_table(table.sort_values("year", ascending=False), 2), hide_index=True)
        ui.download(table, f"{focus}_trade.csv", label="Download this economy (CSV)")

# ------------------------------------------------------------------ openness
with tab_open:
    rows = []
    for iso in chosen:
        e = economy(data, iso).loc[start:end]
        rows.append(pd.DataFrame({"year": e.index, "economy": names[iso], "openness": e["openness"].to_numpy()}))
    long = pd.concat(rows).dropna()
    fig = charts.lines(long, "year", "openness", color="economy", title="Trade openness: (exports + imports) as % of GDP", yaxis_title="% of GDP")
    st.plotly_chart(fig)
    st.caption("Openness above 100% is possible because exports and imports are gross flows (including re-exports and goods processed for export) while GDP is value added.")

# ------------------------------------------------------------------ rankings
with tab_rank:
    c1, c2, c3, c4 = st.columns(4)
    year = c1.slider("Year", 1970, last_year, last_year)
    metric = c2.radio("Rank by", ["US$", "% of GDP"], horizontal=True)
    n = c3.slider("Economies per side", 5, 20, 10)
    min_gdp = c4.slider("Minimum GDP (US$ bn)", 0, 500, 50 if metric == "% of GDP" else 0, 10, help="Applied to the % of GDP ranking so that tiny economies do not dominate.")
    by = "balance" if metric == "US$" else "balance_gdp"
    surplus, deficit = ranking(data, year, by, n, min_gdp=min_gdp * 1e9 if metric != "US$" else 0.0)
    col_s, col_d = st.columns(2)
    for col, tbl, colour, title in [(col_s, surplus, GREEN, "Largest surpluses"), (col_d, deficit, RED, "Largest deficits")]:
        plot = tbl.assign(value=tbl["balance"] / 1e9 if metric == "US$" else tbl["balance_gdp"]).iloc[::-1]
        fig = px.bar(plot, x="value", y="country", orientation="h", color_discrete_sequence=[colour])
        fig.update_layout(hovermode="closest")
        charts.theme(fig, title=f"{title}, {year}", height=420)
        fig.update_xaxes(title_text="US$ billion" if metric == "US$" else "% of GDP")
        fig.update_yaxes(title_text=None)
        col.plotly_chart(fig)
    both = pd.concat([surplus, deficit]).assign(exports_bn=lambda d: d["exports"] / 1e9, imports_bn=lambda d: d["imports"] / 1e9, balance_bn=lambda d: d["balance"] / 1e9)
    st.dataframe(format_table(both[["country", "balance_bn", "balance_gdp", "exports_bn", "imports_bn"]], 1), hide_index=True)
    st.caption("Surpluses first, then deficits. Ireland, Luxembourg and Singapore have very large flows relative to GDP, partly reflecting multinational companies and re-exports.")

# ------------------------------------------------------------------ partners
with tab_partners:
    st.caption(
        "WITS (UN Comtrade) covers **goods only**, valued as each country reports them (imports usually include freight and insurance), "
        "so balances here differ from the goods-and-services figures on the other tabs."
    )
    c1, c2 = st.columns(2)
    reporter = c1.selectbox("Reporter", list(WITS_REPORTERS), format_func=lambda c: WITS_REPORTERS[c])
    trade = wits(reporter)
    years = wits_years(trade)
    year_p = c2.select_slider("Year", options=years, value=years[-1])
    flow = st.radio("Partners by", ["exports", "imports"], horizontal=True)
    tp = top_partners(trade, year_p, flow, 10)
    fig = px.bar(tp.iloc[::-1], x="share", y="name", orientation="h", text=tp.iloc[::-1]["share"].round(1).astype(str) + "%", color_discrete_sequence=[BLUE])
    fig.update_layout(hovermode="closest")
    charts.theme(fig, title=f"{WITS_REPORTERS[reporter]}: top 10 {flow} partners, {year_p} (share of total merchandise {flow})", height=420)
    fig.update_xaxes(title_text="% of total")
    fig.update_yaxes(title_text=None)
    st.plotly_chart(fig)

    conc = concentration(trade, year_p, flow)
    w = world_totals(trade).loc[year_p]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Largest partner share", f"{conc['top1_share']:.1f}%")
    m2.metric("Top-5 share", f"{conc['top5_share']:.1f}%")
    m3.metric("Herfindahl index", f"{conc['hhi']:.0f}", help="Sum of squared shares, 0-10,000. Above 2,500 is highly concentrated.")
    m4.metric("Merchandise balance", f"{w['balance'] / 1e9:+,.0f} bn US$")

    bb = bilateral_balance(trade, year_p)
    extremes = pd.concat([bb.head(8), bb.tail(8)]).drop_duplicates("partner")
    fig = go.Figure(go.Bar(x=extremes["balance"] / 1e9, y=extremes["name"], orientation="h", marker_color=[GREEN if v >= 0 else RED for v in extremes["balance"]]))
    fig.update_layout(yaxis=dict(autorange="reversed"))
    charts.theme(fig, title=f"{WITS_REPORTERS[reporter]}: bilateral merchandise balance, largest surpluses and deficits, {year_p}", yaxis_title=None, height=480)
    fig.update_xaxes(title_text="US$ billion (exports minus imports)")
    fig.update_layout(hovermode="closest")
    st.plotly_chart(fig)
    st.dataframe(format_table(bb.assign(**{c + "_bn": bb[c] / 1e9 for c in ["exports", "imports", "balance", "total_trade"]})[["name", "exports_bn", "imports_bn", "balance_bn", "total_trade_bn"]].head(25), 2), hide_index=True)
    st.caption("Table: the 25 largest bilateral surpluses. Taiwan appears as 'Other Asia, nes' in UN Comtrade. Unspecified and special-category trade is excluded from partner rows.")

# ------------------------------------------------------------------ footer
ui.sources(
    "Exports, imports, net trade, trade/GDP and current account: World Bank WDI (NE.EXP.GNFS.CD, NE.IMP.GNFS.CD, BN.GSR.GNFS.CD, NE.EXP.GNFS.ZS, NE.IMP.GNFS.ZS, NE.TRD.GNFS.ZS, BN.CAB.XOKA.GD.ZS). Goods and services; latest full year 2024.",
    "Trade partners: WITS TradeStats (UN Comtrade) via wits.worldbank.org, merchandise goods only, 18 reporters chosen for size; years vary by reporter (Russia ends 2021). Bilateral balances use each reporter's own statistics, not mirror data.",
    "Partner coverage is limited to the reporters listed; services trade by partner is not available from these sources.",
)
