"""Streamlit front end for the unemployment visualizer. All calculations live in unemployment.py."""

import plotly.express as px
import streamlit as st

import unemployment as un
from core import charts, ui
from core import worldbank as wb

ui.page(
    "Unemployment visualizer",
    "Unemployment by country, gender, age and education: trends, gaps and how much data sits behind each series.",
    icon="👥",
)


@st.cache_data
def load():
    return un.load()


@st.cache_data
def country_names() -> dict[str, str]:
    return wb.names()


df = load()
names = country_names()
years = df["total"].dropna().index.get_level_values("year")
first_year, last_year = int(years.min()), int(years.max())  # years in which the main series exist
default_year = un.default_year(df)

with_data = {iso: names.get(iso, iso) for iso in df.index.get_level_values("iso3").unique()}
countries = ui.country_picker(with_data, ["USA", "GBR", "DEU", "JPN", "ZAF", "IND", "BRA"])
start, end = ui.year_range(first_year, last_year, (2000, last_year))
year = st.sidebar.slider("Year for comparisons", first_year, last_year, default_year, help="Used by the education chart, the 'Largest gaps' tab, the table and the download.")
if year > default_year:
    st.sidebar.caption(f"Education data thin out after {default_year}: only a few economies report {year}.")

cs = un.cross_section(df, year, names)
gender = un.gender_summary(df, year) if cs["gender_gap"].notna().any() else None

m1, m2, m3 = st.columns(3)
if gender:
    m1.metric(f"Economies with data, {year}", gender["economies"])
    m2.metric("Female rate above male rate", f"{gender['female_higher']} of {gender['economies']}", f"median gap {gender['median_gap_pp']:+.2f} pp", delta_color="off")
    m3.metric("Median youth / all-ages rate", f"{cs['youth_ratio'].median():.1f}x", f"youth {cs['youth'].median():.1f}% vs all ages {cs['total'].median():.1f}%", delta_color="off")
else:
    st.warning(f"No unemployment data for {year}.")

tab_trend, tab_gap, tab_edu, tab_rank = st.tabs(["Trends", "Gender and youth", "Education", "Largest gaps"])

# ---------------------------------------------------------------------------- trends
with tab_trend:
    series = st.selectbox("Series", ["total", "female", "male", "youth"], format_func=un.LABELS.get)
    data = un.trend(df, countries, series, start, end)
    if data.empty:
        st.info("Pick at least one country with data in this window.")
    else:
        data["country"] = data["iso3"].map(names)
        fig = charts.lines(data, "year", "value", "country", markers=True, yaxis_title=f"Unemployment, {un.LABELS[series].lower()} (%)")
        st.plotly_chart(fig, width="stretch")
        st.caption("ILO modelled estimates: the ILO imputes years without a labour force survey, and the latest years are estimates that may be revised.")

# ---------------------------------------------------------------------------- gender and youth
with tab_gap:
    for column, title, ref_name, zero in (
        ("gender_gap", "Gender gap: female minus male unemployment (percentage points)", "Median of all economies", 0),
        ("youth_ratio", "Youth unemployment as a multiple of the all-ages rate", "Median of all economies", 1),
    ):
        data = un.trend(df, countries, column, start, end)
        if data.empty:
            st.info("Pick at least one country with data in this window.")
            continue
        data["country"] = data["iso3"].map(names)
        fig = charts.lines(data, "year", "value", "country", markers=True, yaxis_title=un.LABELS[column])
        median = un.median_by_year(df, column).loc[start:end]
        fig.add_scatter(x=median.index, y=median.values, name=ref_name, mode="lines", line=dict(color="#111827", dash="dash"))
        fig.add_hline(y=zero, line_dash="dot", line_color="#9ca3af")
        st.subheader(title)
        st.plotly_chart(fig, width="stretch")
    st.caption(
        "Above zero in the first chart means women have the higher rate. The youth multiple divides the 15-24 rate by the 15+ rate "
        "(which includes the young), so it understates the youth-to-adult (25+) ratio."
    )

# ---------------------------------------------------------------------------- education
with tab_edu:
    options = [iso for iso in sorted(with_data, key=with_data.get) if un.education_years(df, iso)]
    preferred = next((c for c in countries if c in options), "USA")
    country = st.selectbox("Country", options, index=options.index(preferred), format_func=with_data.get)
    used, profile = un.education_profile(df, country, year)
    complete = un.education_complete_count(df, year)
    if used is None:
        st.warning(
            f"{with_data[country]} reports no education-specific unemployment rate in {year} or the {un.MAX_EDUCATION_AGE} years before. "
            f"Years with data: {', '.join(map(str, un.education_years(df, country))) or 'none'}."
        )
    else:
        if used != year:
            st.info(f"No education data for {with_data[country]} in {year}; showing {used}, the latest year within {un.MAX_EDUCATION_AGE} years.")
        bars = profile.rename(index=un.LABELS).rename("rate").reset_index().rename(columns={"index": "group"})
        fig = px.bar(bars, x="group", y="rate", text_auto=".1f", labels={"group": "", "rate": "Unemployment rate (%)"})
        fig.update_traces(marker_color=["#2563eb", "#7c3aed", "#16a34a", "#9ca3af"][: len(bars)])
        fig.update_layout(hovermode="closest")
        st.plotly_chart(charts.theme(fig, title=f"{with_data[country]}, {used}", height=380), width="stretch")
    over_time = df.loc[country, un.EDUCATION].dropna(how="all").reset_index().melt("year", var_name="group", value_name="rate")
    over_time["group"] = over_time["group"].map(un.LABELS)
    if not over_time.empty:
        fig = charts.lines(over_time.dropna(), "year", "rate", "group", markers=True, yaxis_title="Unemployment rate (%)")
        st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Education series come from the ILO's labour force surveys, so a country-year exists only where a survey does. In {year}, "
        f"{complete} economies report all three education rates (out of {un.economy_count()} economies in the World Bank list)."
    )

# ---------------------------------------------------------------------------- largest gaps
with tab_rank:
    measure = st.radio("Measure", ["gender_gap", "youth_ratio", "education_gap"], format_func=un.LABELS.get, horizontal=True)
    n = st.slider("Countries to show", 5, 25, 10)
    if measure == "education_gap":
        frame = un.education_snapshot(df, year, names=names)
        st.caption(f"Latest complete education record up to {un.MAX_EDUCATION_AGE} years back from {year}; the year used is shown. {len(frame)} economies qualify.")
        extra = ["year_used"]
    else:
        frame = cs
        extra = []
    explain = {
        "gender_gap": ("Women worst off (female rate above male)", "Men worst off (male rate above female)"),
        "youth_ratio": ("Youth rate highest relative to all ages", "Youth rate lowest relative to all ages"),
        "education_gap": ("Basic education worst off relative to advanced", "Advanced education worst off relative to basic"),
    }[measure]
    cols = ["country", measure, *extra]
    left, right = st.columns(2)
    for slot, label, ascending in ((left, explain[0], False), (right, explain[1], True)):
        top = un.largest(frame, measure, n, ascending=ascending)
        with slot:
            st.subheader(label)
            if top.empty:
                st.write("No data for this year.")
                continue
            fig = px.bar(top.iloc[::-1], x=measure, y="country", orientation="h", labels={measure: un.LABELS[measure], "country": ""})
            fig.update_traces(marker_color="#dc2626" if not ascending else "#2563eb")
            fig.update_layout(hovermode="closest")
            st.plotly_chart(charts.theme(fig, height=max(300, 26 * len(top) + 80)), width="stretch")

# ---------------------------------------------------------------------------- table, coverage, download
st.subheader(f"Selected countries, {year}")
table = cs[cs["iso3"].isin(countries)].drop(columns="iso3")
if table.empty:
    st.write("None of the selected countries reports data for this year.")
else:
    st.dataframe(table.rename(columns=un.LABELS).rename(columns={"country": "Country"}).round(2), hide_index=True, width="stretch")

with st.expander("Data coverage"):
    st.dataframe(
        un.coverage_table(df, un.economy_count()).rename(
            columns={
                "series": "Series",
                "indicator": "Indicator",
                "economies": "Economies",
                "share_of_economies_pct": "% of economies",
                "observations": "Observations",
                "first_year": "First year",
                "last_year": "Last year",
                "median_years_per_economy": "Median years per economy",
                "economies_with_10plus_years": "Economies with 10+ years",
            }
        ).round(1),
        hide_index=True,
        width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%d") for c in ("First year", "Last year")},
    )
    per_year = un.economies_per_year(df, ["total", *un.EDUCATION]).loc[1991:].rename(columns=un.LABELS)
    fig = px.line(per_year.reset_index().melt("year", var_name="series", value_name="economies"), x="year", y="economies", color="series")
    st.plotly_chart(charts.theme(fig, yaxis_title="Economies reporting"), width="stretch")

ui.download(cs, f"unemployment_{year}.csv", label=f"Download all economies, {year} (CSV)")
ui.sources(
    "World Bank WDI: SL.UEM.TOTL.ZS, SL.UEM.TOTL.FE.ZS, SL.UEM.TOTL.MA.ZS, SL.UEM.1524.ZS (ILO modelled estimates); SL.UEM.BASC.ZS, SL.UEM.INTM.ZS, SL.UEM.ADVN.ZS (ILO Education and Mismatch Indicators, survey-based).",
    "Education series cover about half of economies in a given year and not every year; rankings fall back to the latest record within five years and say which year was used.",
    "Youth multiple = youth rate / all-ages rate, which understates the youth-to-adult ratio. Definitions of unemployment and education levels follow ILO standards but survey quality varies.",
)
