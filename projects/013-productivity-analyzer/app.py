"""Streamlit app for the Productivity Analyzer. Widgets and charts only; the analysis lives in productivity.py."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import productivity as pr
from core import charts, ui
from core import worldbank as wb

ui.page(
    "Productivity Analyzer",
    "Output per worker and per hour across countries, the gap between sectors, and how much of growth came from workers changing sector.",
    icon="🏭",
)


@st.cache_data
def load_all():
    wide = pr.load()
    hours = pr.load_hours()
    pe = pr.level_matrix(wide, "gdp_pe")
    return wide, pe, pr.gdp_per_hour(pe, hours), pr.load_us_output_per_hour()


wide, per_worker, per_hour, us_oph = load_all()
names = wb.names()
available = {c: names[c] for c in per_worker.columns if c in names}

# ------------------------------------------------------------------------------------ sidebar

chosen = ui.country_picker(available, ["USA", "DEU", "JPN", "BRA", "CHN", "IND", "NGA", "KOR"])
start, end = ui.year_range(1991, int(per_worker.index.max()), (2000, 2019))
measure = st.sidebar.radio(
    "Output measure",
    ["Per worker (World Bank, to 2025)", "Per hour worked (estimate, to 2023)"],
    help="Per hour divides GDP per person employed by Penn World Table annual hours per engaged person. "
    "It joins two sources, so treat it as an estimate.",
)
levels = per_worker if measure.startswith("Per worker") else per_hour
unit = "2021 PPP $ per worker" if measure.startswith("Per worker") else "2021 PPP $ per hour"

if not chosen:
    st.info("Pick at least one country in the sidebar.")
    st.stop()
if "USA" not in chosen:
    st.caption("The United States is always used as the benchmark, whether or not it is selected.")
if end <= start:
    st.warning("Choose a window of at least two years.")
    st.stop()

# ------------------------------------------------------------------------------------ levels and growth

rel = pr.relative_to_benchmark(levels)
shown = [c for c in chosen if c in rel.columns]
missing = [available[c] for c in chosen if c not in rel.columns]
if missing:
    st.caption(f"No hours data for: {', '.join(missing)}.")

left, right = st.columns(2)
rel_long = rel[shown].loc[start:end].rename(columns=names).reset_index().melt("year", var_name="country", value_name="us100")
left.plotly_chart(
    charts.lines(rel_long.dropna(), "year", "us100", "country", title=f"Productivity relative to the US (US = 100), {unit}"),
    width="stretch",
)

growth = pr.window_cagr(levels, start, end)
g_shown = growth.reindex(shown).dropna()
growth_fig = charts.bars(
    pd.DataFrame({"country": [names[c] for c in g_shown.index], "cagr": g_shown.to_numpy()}).sort_values("cagr"),
    "country",
    "cagr",
    title=f"Average annual growth {start}-{end} (%, compound)",
)
growth_fig.add_hline(y=float(growth.median()), line_dash="dot", annotation_text=f"median of {growth.notna().sum()} economies")
right.plotly_chart(growth_fig, width="stretch")
if len(g_shown) < len(shown):
    st.caption(f"Growth is blank where {start} or {end} is missing: {', '.join(names[c] for c in shown if c not in g_shown.index)}.")

# ------------------------------------------------------------------------------------ sector gaps and shift-share

sectors = pr.sector_table(wide, end)
sector_iso = [c for c in chosen if c in sectors.index]
left, right = st.columns(2)

if sector_iso:
    fig = go.Figure()
    for s in pr.SECTORS:
        fig.add_bar(name=pr.SECTOR_NAMES[s], x=[names[c] for c in sector_iso], y=sectors.loc[sector_iso, f"va_{s}"])
    fig.update_yaxes(type="log")
    fig.update_layout(barmode="group", hovermode="closest")
    left.plotly_chart(
        charts.theme(fig, title=f"Value added per worker by sector, {end} (constant 2015 US$, log scale)", height=460),
        width="stretch",
    )
else:
    left.info(f"No sector data for the selected countries in {end}.")
no_sector = [names[c] for c in chosen if c not in sectors.index]
if no_sector:
    left.caption(f"No complete sector data in {end}: {', '.join(no_sector)}. The US has sector value added for 2015 only.")

ss = pr.shift_share_window(wide, start, end)
ss_iso = [c for c in chosen if c in ss.index]
if ss_iso:
    parts = {"within_pp": "Within sectors", "between_pp": "Between sectors", "interaction_pp": "Interaction"}
    fig = go.Figure()
    for col, label in parts.items():
        fig.add_bar(name=label, x=[names[c] for c in ss_iso], y=ss.loc[ss_iso, col])
    fig.update_layout(barmode="relative", hovermode="closest")
    right.plotly_chart(
        charts.theme(fig, title=f"What drove productivity growth {start}-{end} (percentage points of growth)", height=460),
        width="stretch",
    )
else:
    right.info(f"No complete sector data for the selected countries in both {start} and {end}.")

# ------------------------------------------------------------------------------------ table and download

table = pd.DataFrame({"country": [names[c] for c in shown], "iso3": shown})
table[f"level_{end}"] = [levels[c].get(end) for c in shown]
table[f"us100_{end}"] = [rel[c].get(end) for c in shown]
table[f"cagr_{start}_{end}_pct"] = [growth.get(c) for c in shown]
if sector_iso:
    gaps = sectors[["ind_to_agr", "srv_to_agr", "apg"]].rename(columns=lambda c: f"{c}_{end}")
    table = table.join(gaps, on="iso3")
table = table.join(ss[["growth_pct", "within_pp", "between_pp", "interaction_pp"]].add_suffix(f"_{start}_{end}"), on="iso3")
st.dataframe(table.set_index("country").drop(columns="iso3").round(2), width="stretch")
ui.download(table.round(4), f"productivity_{start}_{end}.csv")

if len(us_oph):
    last = int(us_oph.index.max())
    first = max(start, int(us_oph.index.min()))
    last_in_window = min(end, last)
    if last_in_window > first:
        oph = (us_oph.loc[last_in_window] / us_oph.loc[first]) ** (1 / (last_in_window - first)) - 1
        st.caption(
            f"United States, nonfarm business output per hour (FRED OPHNFB): {oph:.2%} a year, {first}-{last_in_window}. "
            "Different scope from the whole-economy figures above, so it is a cross-check, not the same number."
        )

ui.sources(
    "World Bank WDI: GDP per person employed (SL.GDP.PCAP.EM.KD, 2021 PPP $); value added per worker by sector (NV.AGR/IND/SRV.EMPL.KD, 2015 US$); employment shares (SL.AGR/IND/SRV.EMPL.ZS, modelled ILO estimates).",
    "Hours: Penn World Table average annual hours per person engaged (FRED AVHWPE<ISO2>A065NRUG), 60 countries, to 2023. US output per hour: FRED OPHNFB.",
    "Limits: only three broad sectors; sector series are in market-rate US$ and the headline series in PPP $; the US has no sector series after 2015; "
    "employment shares are modelled estimates; per-hour levels join two sources; shift-share is an accounting split, not a causal one.",
)
