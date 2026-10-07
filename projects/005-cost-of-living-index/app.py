"""Streamlit app for the Cost of Living Index. Widgets and charts only; the analysis lives in cost_of_living.py."""

import plotly.graph_objects as go
import streamlit as st

import cost_of_living as col
from core import charts, ui

ui.page(
    "Cost of Living Index",
    "What does the same basket of everyday goods and services cost in one place compared with another?",
    icon="🛒",
)
st.info(
    "**There is no open city-level price dataset for the world**, so this app has two separate parts. "
    "**US metro areas** are genuine city-level data (Bureau of Economic Analysis). "
    "**Countries** use World Bank and Big Mac data, and are country averages, not city prices: "
    "a country figure says nothing about its capital or any particular city."
)


@st.cache_data
def load():
    return col.metro_panel(col.load_bea()), col.country_panel(col.country_table())


metros, countries = load()


def comparison_chart(cmp, a: str, b: str, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=cmp.index, y=cmp["A"], name=a)
    fig.add_bar(x=cmp.index, y=cmp["B"], name=b)
    fig.add_hline(y=100, line_dash="dash", line_color="#9ca3af", annotation_text="benchmark = 100")
    fig.update_layout(barmode="group", hovermode="closest")
    return charts.theme(fig, title=title, yaxis_title="Price level index")


def pair_section(snap, measures: dict[str, str], default_a: str, default_b: str, key: str, title: str, salary_note: str) -> None:
    """Two-place comparison: pick A and B, enter a salary, see the equivalent and the breakdown."""
    places = sorted(snap.index)
    left, mid, right = st.columns([2, 2, 1])
    a = left.selectbox("Place A (where the salary is earned)", places, index=places.index(default_a) if default_a in places else 0, key=f"{key}_a")
    b = mid.selectbox("Place B (where you would move)", places, index=places.index(default_b) if default_b in places else 1, key=f"{key}_b")
    salary = right.number_input("Salary in A", min_value=1000, value=100_000, step=5_000, key=f"{key}_salary")
    measure = st.radio("Price measure used for the equivalent salary", list(measures), format_func=measures.get, horizontal=True, key=f"{key}_measure") if len(measures) > 1 else next(iter(measures))
    try:
        cmp = col.comparison(snap, a, b)
    except KeyError as err:
        st.warning(str(err))
        return
    if measure not in cmp.index:
        st.warning(f"No {measures[measure]} figure for both places in this year; try another measure.")
        return
    price_a, price_b = cmp.loc[measure, "A"], cmp.loc[measure, "B"]
    equivalent = col.equivalent_salary(salary, price_a, price_b)
    c1, c2, c3 = st.columns(3)
    c1.metric("Equivalent salary in B", f"{equivalent:,.0f}", delta=f"{equivalent / salary - 1:+.1%} vs A")
    c2.metric("Price index, A", f"{price_a:.1f}")
    c3.metric("Price index, B", f"{price_b:.1f}")
    st.caption(f"{salary:,.0f} earned in {a} buys the same {measures[measure].lower()} basket as {equivalent:,.0f} in {b}. {salary_note}")
    labelled = cmp.rename(index=measures)
    st.plotly_chart(comparison_chart(labelled, a, b, title), width="stretch")


def ranking_section(snap, measure: str, label: str, n: int, filename: str) -> None:
    ranked = col.rank_table(snap, measure)
    shown = ranked.rename(columns={"place": "Place", "rank": "Rank", "index": "Index", "vs_100": "Difference from 100"}).round(1)
    left, right = st.columns(2)
    left.markdown(f"**Most expensive {n}** ({label})")
    left.dataframe(shown.head(n), hide_index=True, width="stretch")
    right.markdown(f"**Least expensive {n}**")
    right.dataframe(shown.tail(n).iloc[::-1], hide_index=True, width="stretch")
    ui.download(shown, filename, label="Download full ranking (CSV)")


def history_section(panel, picked: list[str], measure: str, years: tuple[int, int], label: str, note: str) -> None:
    if not picked:
        st.info("Pick places in the sidebar to see how their price level changed.")
        return
    data = col.history(panel, picked, measure)
    data = data[data["year"].between(*years)]
    st.plotly_chart(charts.lines(data, x="year", y="value", color="place", title=f"{label} over time", yaxis_title="Price level index"), width="stretch")
    st.caption(note)


# --------------------------------------------------------------------------- sidebar

metro_names = sorted(metros.index.get_level_values("place").unique())
country_names = sorted(countries.index.get_level_values("place").unique())
metro_years = metros.index.get_level_values("year")
country_year_values = countries["household"].dropna().index.get_level_values("year")

st.sidebar.header("US metro areas")
picked_metros = st.sidebar.multiselect(
    "Metro areas to track over time",
    metro_names,
    default=[m for m in ("New York-Newark-Jersey City, NY-NJ", "San Francisco-Oakland-Fremont, CA", "Dallas-Fort Worth-Arlington, TX", "Miami-Fort Lauderdale-West Palm Beach, FL") if m in metro_names],
)
metro_range = ui.year_range(int(metro_years.min()), int(metro_years.max()), key="metro_years")
st.sidebar.header("Countries")
default_countries = ["United States", "Switzerland", "Germany", "Japan", "India", "Brazil"]
picked_countries = st.sidebar.multiselect("Countries to track over time", country_names, default=[c for c in default_countries if c in country_names])
country_range = ui.year_range(int(country_year_values.min()), int(country_year_values.max()), (2000, int(country_year_values.max())), key="country_years")

tab_metro, tab_country = st.tabs(["US metro areas (city-level)", "Countries (country averages)"])

# --------------------------------------------------------------------------- tab 1: metros

with tab_metro:
    st.subheader("US metropolitan areas")
    st.write(
        "Regional price parities (RPPs) express the price level of a metro area as a percentage of the US average (100), "
        "for all items and for goods, housing, utilities and other services. Areas are whole metropolitan statistical areas, "
        "not city limits."
    )
    year = st.select_slider("Year", options=sorted(metro_years.unique()), value=int(metro_years.max()), key="metro_year")
    snap = col.snapshot(metros, year)
    pair_section(
        snap,
        {"All items": "All items"},
        "New York-Newark-Jersey City, NY-NJ",
        "Dallas-Fort Worth-Arlington, TX",
        "metro",
        f"Price level by component, {year} (US average = 100)",
        "It matches the average basket, not your own: housing dominates the differences between metros.",
    )
    st.subheader("Most and least expensive metro areas")
    component = st.radio("Component", list(col.BEA_COMPONENTS.values()), horizontal=True, key="metro_component")
    ranking_section(snap, component, f"{component}, {year}", 10, f"metro_ranking_{year}.csv")
    st.subheader("Change over time")
    history_section(
        metros,
        picked_metros,
        component,
        metro_range,
        f"{component} price level",
        "Each year is measured against that year's US average, so a falling line means prices rose more slowly than the US average, not that prices fell.",
    )

# --------------------------------------------------------------------------- tab 2: countries

with tab_country:
    st.subheader("Countries")
    st.write(
        "Price level indices with the **United States = 100**, at market exchange rates. The World Bank measures price "
        "levels from the International Comparison Program's survey of comparable goods and services; the Big Mac index "
        "prices one product in about 50 economies."
    )
    year_options = sorted(country_year_values.unique())
    default_year = col.latest_year(countries, "household")
    year = st.select_slider("Year", options=year_options, value=default_year, key="country_year")
    snap = col.snapshot(countries, year)
    pair_section(
        snap,
        col.COUNTRY_MEASURES,
        "United States",
        "Germany",
        "country",
        f"Price level by measure, {year} (United States = 100)",
        "Salaries are in US dollars at market exchange rates; the figure is a country average, not a city.",
    )
    st.subheader("Most and least expensive countries")
    measure = st.radio("Measure", list(col.COUNTRY_MEASURES), format_func=col.COUNTRY_MEASURES.get, horizontal=True, key="country_rank_measure")
    ranking_section(snap, measure, f"{col.COUNTRY_MEASURES[measure]}, {year}", 10, f"country_ranking_{year}.csv")
    agree = col.measure_agreement(snap)
    if agree["n"] >= 10:
        st.caption(
            f"Across the {agree['n']} countries with both a World Bank household price level and a Big Mac price in {year}, "
            f"the two rankings correlate at {agree['spearman']:.2f} (Spearman). The Big Mac is a single traded good, "
            f"so it varies less with local services and wages than the household basket."
        )
    st.subheader("Change over time")
    history_section(
        countries,
        picked_countries,
        "household",
        country_range,
        "Household price level",
        "Relative to the United States. Large moves usually reflect exchange-rate swings, and the World Bank extrapolates "
        "price levels between International Comparison Program benchmark years.",
    )

ui.sources(
    "US metro areas: Bureau of Economic Analysis, Regional Price Parities by MSA (table MARPP, 2008-2024), US government data in the public domain (source: U.S. Bureau of Economic Analysis).",
    "Countries: World Bank price level index for household consumption (`PA.NUS.PRVT.PLI`) and GDP (`PA.NUS.GDP.PLI`), International Comparison Program, CC BY 4.0; Big Mac index by The Economist (CC BY).",
    "Limits: no open worldwide city-level data exists, so cities outside the US cannot be compared. Index values are price levels for an average basket and cannot capture quality, lifestyle, taxes or wages.",
)
