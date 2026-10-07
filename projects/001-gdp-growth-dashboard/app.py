"""Streamlit front end for the GDP growth dashboard. All calculations live in gdp_growth.py."""

import plotly.express as px
import streamlit as st

import gdp_growth as gg
from core import charts, ui
from core import worldbank as wb

ui.page("GDP growth dashboard", "Compare real GDP growth across countries and years: compound growth, volatility and recessions.", icon="📈")


@st.cache_data
def load(measure: str):
    return gg.load(measure)


@st.cache_data
def country_names() -> dict[str, str]:
    return wb.names()


measure = st.sidebar.radio("Measure", list(gg.MEASURES), help="Total GDP, or GDP divided by population.")
labels = gg.MEASURES[measure]
df = load(measure)
names = country_names()
cov = gg.world_coverage(df)

available = {iso: names.get(iso, iso) for iso in df.index.get_level_values("iso3").unique()}
countries = ui.country_picker(available, gg.DEFAULT_COUNTRIES)
first_year = cov["first_year"]
start, end = ui.year_range(first_year, cov["last_year"], (2000, cov["last_full_year"]))
st.sidebar.caption(f"The level in {start} is the base. Growth is measured over {start + 1}-{end}.")
min_size = 0
if measure == "GDP":
    min_size = st.sidebar.select_slider(
        "Ranking: smallest economy included",
        options=[0, 1, 10, 50, 100],
        value=10,
        format_func=lambda v: "all economies" if v == 0 else f"base-year GDP of at least ${v}bn",
        help="Tiny economies can post huge growth rates. Raising the threshold changes the ranking and scatter only.",
    )

if not countries:
    st.info("Pick at least one country in the sidebar.")
    st.stop()
if end <= start:
    st.info("Pick a window of at least two years.")
    st.stop()

table = gg.summary(df, countries, start, end, names)
ranking = gg.rank_economies(df, start, end, min_start_level_bn=min_size, names=names)
table = table.merge(ranking[["iso3", "rank"]], on="iso3", how="left")
table["rank"] = table["rank"].astype("Int64")

with_cagr = table.dropna(subset=["cagr_pct"])
if with_cagr.empty:
    st.warning(f"None of the selected countries has a GDP level in both {start} and {end}. Try another window.")
else:
    best = with_cagr.sort_values("cagr_pct", ascending=False).iloc[0]
    steady = table.dropna(subset=["volatility_pp"]).sort_values("volatility_pp").iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Fastest compound growth", best["country"], f"{best['cagr_pct']:.2f}% a year")
    m2.metric("Most stable growth", steady["country"], f"std dev {steady['volatility_pp']:.2f} pp")
    m3.metric("Recession years in window", int(table["recession_years"].sum()), f"across {len(countries)} countries", delta_color="off")

growth = df["growth"].unstack("iso3")[countries].loc[start + 1 : end]
growth_long = growth.stack().rename("growth").reset_index().rename(columns={"iso3": "country"})
growth_long["country"] = growth_long["country"].map(names)

tab_growth, tab_level, tab_scatter = st.tabs(["Annual growth", "GDP level (base = 100)", "Growth vs volatility"])

with tab_growth:
    fig = charts.lines(growth_long, "year", "growth", "country", markers=True, yaxis_title=labels["growth_label"])
    fig.add_hline(y=0, line_dash="dot", line_color="#4b5563")
    st.plotly_chart(fig, width="stretch")
    st.caption("Points below the dotted zero line are recession years (negative annual growth).")

with tab_level:
    rebased = gg.rebased_levels(df, countries, start, end)
    rebased["country"] = rebased["iso3"].map(names)
    fig = charts.lines(rebased, "year", "index", "country", yaxis_title=f"{labels['level_label']}, {start} = 100")
    st.plotly_chart(fig, width="stretch")

with tab_scatter:
    everyone = ranking.assign(selected=ranking["iso3"].isin(countries).map({True: "Selected", False: "Other economies"}))
    fig = px.scatter(
        everyone,
        x="volatility_pp",
        y="cagr_pct",
        color="selected",
        hover_name="country",
        color_discrete_map={"Selected": "#dc2626", "Other economies": "#9ca3af"},
        labels={"volatility_pp": "Volatility: std dev of annual growth (pp)", "cagr_pct": "CAGR (% a year)", "selected": ""},
    )
    chosen = everyone[everyone["selected"] == "Selected"]
    fig.add_scatter(x=chosen["volatility_pp"], y=chosen["cagr_pct"], text=chosen["country"], mode="text", textposition="top center", showlegend=False)
    fig.update_layout(hovermode="closest")
    st.plotly_chart(charts.theme(fig), width="stretch")
    st.caption(f"{len(ranking)} economies with a level in both {start} and {end}" + ("" if min_size == 0 else f" and base-year GDP of at least ${min_size}bn") + ".")

st.subheader(f"Summary, {start}-{end}")
show = table.rename(
    columns={
        "country": "Country",
        "cagr_pct": "CAGR (%)",
        "mean_growth_pct": "Average of annual growth (%)",
        "volatility_pp": "Volatility (pp)",
        "recession_years": "Recession years",
        "worst_year": "Worst year",
        "worst_growth_pct": "Worst growth (%)",
        "rank": f"Rank by CAGR (of {len(ranking)})",
        "years_with_data": "Years with data",
        "years_expected": "Years expected",
    }
).drop(columns=["iso3", "best_year", "best_growth_pct"])
st.dataframe(show.round(2), hide_index=True, width="stretch", column_config={"Worst year": st.column_config.NumberColumn(format="%d")})
st.caption(
    "CAGR is computed from the first and last GDP levels, so it is the compound rate. "
    "The average of annual rates is normally a little higher, and the gap widens with volatility."
)

left, right = st.columns(2)
with left:
    st.subheader("Decade averages (%)")
    decades = gg.decade_table(df, countries).rename(columns=names)
    st.dataframe(decades.round(1), width="stretch")
    st.caption(f"Mean of annual growth rates. Blank where fewer than {gg.MIN_DECADE_OBS} years exist; 2020s are incomplete.")
with right:
    st.subheader("Recession years in window")
    recessions = gg.recession_table(df, countries, start, end, names)
    if recessions.empty:
        st.write("No negative-growth years for the selected countries in this window.")
    else:
        by_country = recessions.groupby("country")["year"].apply(lambda y: ", ".join(map(str, y))).rename("Years with negative growth")
        st.dataframe(by_country, width="stretch")

with st.expander("Data coverage"):
    st.write(
        f"{cov['economies']} economies report {measure.lower()} growth between {cov['first_year']} and {cov['last_year']}; "
        f"{cov['economies_in_last_year']} of them already report {cov['last_year']}. "
        f"The slider opens on {cov['last_full_year']}, the latest year reported by at least 90% of economies."
    )
    coverage = gg.coverage(df, countries, start, end, names).rename(
        columns={
            "country": "Country",
            "first_year": "First year",
            "last_year": "Last year",
            "years_in_window": "Years in window",
            "years_expected": "Years expected",
        }
    )
    year_format = st.column_config.NumberColumn(format="%d")
    st.dataframe(coverage, hide_index=True, width="stretch", column_config={"First year": year_format, "Last year": year_format})

ui.download(show, f"gdp_growth_summary_{start}_{end}.csv")
ui.sources(
    "World Bank, World Development Indicators: NY.GDP.MKTP.KD.ZG, NY.GDP.MKTP.KD, NY.GDP.PCAP.KD.ZG, NY.GDP.PCAP.KD (constant 2015 US$).",
    "Annual data cannot show quarterly 'technical' recessions, and constant-dollar levels are not adjusted for purchasing power.",
    "Coverage differs by country: a country with missing years is summarised on the years it has, and its CAGR is blank if either end level is missing.",
)
