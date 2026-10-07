"""Streamlit app for the Purchasing Power Explorer. Widgets and charts only; the analysis lives in purchasing_power.py."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import purchasing_power as pp
from core import charts, ui

ui.page(
    "Purchasing Power Explorer",
    "How much can a currency actually buy? Market exchange rates against purchasing power parity (PPP).",
    icon="💱",
)


@st.cache_data
def load():
    panel = pp.build_panel()
    releases = pp.bigmac_releases()
    return panel, releases, pp.bigmac_annual(releases), pp.regions()


panel, releases, annual, region = load()
names = dict(zip(panel["iso3"], panel["country"]))

# --------------------------------------------------------------------------- sidebar

years = sorted(panel.dropna(subset=["price_level"])["year"].unique())
default_year = pp.latest_complete_year(panel)
year = st.sidebar.select_slider("Year (World Bank data)", options=[int(y) for y in years], value=default_year, key="pp_year")
picked = ui.country_picker(names, default=["USA", "CHE", "DEU", "CHN", "IND", "BRA", "NGA"], key="pp_countries", label="Countries to highlight")
snap = pp.year_slice(panel, year)

tab_convert, tab_value, tab_income, tab_penn = st.tabs(
    ["Converter", "Over/undervaluation", "Income: nominal vs PPP", "Price level vs income"]
)

# --------------------------------------------------------------------------- converter

with tab_convert:
    candidates = snap.dropna(subset=["ppp", "fx"])
    candidates = candidates[candidates["consistent"]]
    options = sorted(candidates.index, key=lambda c: names[c])
    left, right = st.columns(2)
    iso3 = left.selectbox("Country Y", options, index=options.index("IND") if "IND" in options else 0, format_func=names.get, key="pp_country")
    amount = right.number_input("Amount in US dollars", min_value=1.0, value=100.0, step=10.0)
    row = candidates.loc[iso3]
    conv = pp.convert(amount, row["ppp"], row["fx"])
    a, b, c = st.columns(3)
    a.metric("At market exchange rate", f"{conv.market_lcu:,.1f} local units", help=f"{row['fx']:,.3f} local units per US$ ({year} average).")
    b.metric(f"At PPP: same buying power as US$ {amount:,.0f} in the US", f"{conv.ppp_lcu:,.1f} local units", help=f"{row['ppp']:,.3f} local units per international $ ({year}).")
    c.metric("Market-rate amount buys locally what costs", f"US$ {conv.purchasing_power:,.0f} in the US", delta=f"x{conv.multiplier:.2f}", help="The market-rate amount buys goods in Y that would cost this much at US prices.")
    st.markdown(
        f"At market rates, US$ {amount:,.0f} becomes **{conv.market_lcu:,.1f}** local units in {names[iso3]}. "
        f"Buying the same basket there as US$ {amount:,.0f} buys in the US would cost only **{conv.ppp_lcu:,.1f}** units at PPP, "
        f"so the dollars go {'further' if conv.multiplier > 1 else 'less far'} than their face value: the price level is "
        f"{row['price_level']:.1f} where the US is 100."
    )
    us_bm = releases[releases["iso3"] == "USA"]
    rel = releases[(releases["iso3"] == iso3) & (releases["date"].dt.year == year)]
    if not rel.empty:
        last = rel.sort_values("date").iloc[-1]
        us_price = us_bm[us_bm["date"] == last["date"]]["dollar_price"].iloc[0]
        st.caption(
            f"Big Mac check ({last['date']:%B %Y}): US$ {amount:,.0f} buys {pp.big_macs(amount, last['dollar_price']):,.0f} Big Macs in {names[iso3]} "
            f"against {pp.big_macs(amount, us_price):,.0f} in the US."
        )
    st.caption("Countries with a currency-unit mismatch between the PPP and exchange-rate series are not offered; see the footer.")

# --------------------------------------------------------------------------- over/undervaluation

with tab_value:
    basis = st.radio(
        "Basis",
        ["Big Mac, raw index", "Big Mac, GDP-adjusted index", "World Bank price level (PPP / exchange rate)"],
        horizontal=True,
        key="pp_basis",
    )
    if basis.startswith("Big Mac"):
        dates = sorted(releases["date"].drop_duplicates(), reverse=True)
        date = st.selectbox("Release", dates, format_func=lambda d: f"{d:%B %Y}")
        col = "USD_raw" if "raw" in basis else "USD_adjusted"
        data = releases[releases["date"] == date].dropna(subset=[col]).rename(columns={"name": "country", col: "valuation"})
        sub = f"Big Mac index, {date:%B %Y}"
    else:
        data = snap[snap["consistent"]].dropna(subset=["price_level"]).assign(valuation=lambda d: pp.ppp_valuation(d["price_level"])).reset_index()
        sub = f"PPP price level, {year}"
    data = data.sort_values("valuation")
    data["colour"] = np.where(data["valuation"] < 0, "Undervalued vs US$", "Overvalued vs US$")
    fig = charts.bars(
        data.assign(pct=data["valuation"] * 100),
        x="country",
        y="pct",
        color="colour",
        color_discrete_map={"Undervalued vs US$": "#dc2626", "Overvalued vs US$": "#2563eb"},
        title=f"Currency over/undervaluation against the US dollar: {sub}",
        yaxis_title="% over (+) or under (-) valued",
    )
    fig.update_xaxes(title_text="", tickangle=-60, categoryorder="total ascending")
    st.plotly_chart(fig, width="stretch")
    st.caption("Negative: the currency buys more at home than its exchange rate suggests, so local prices are lower than US prices.")

    merged = pp.crosscheck_bigmac(panel, year, annual)
    st.subheader("Cross-check: our price level against the Big Mac")
    if len(merged) < 10:
        st.info("Too few countries have both a price level and a Big Mac price in this year (the Big Mac data start in 2000).")
    else:
        stats = pp.crosscheck_summary(merged)
        scatter = go.Figure()
        scatter.add_scatter(x=merged["price_level"], y=merged["bigmac_level"], mode="markers", text=merged["country"], marker=dict(size=9), name="Countries")
        top = float(max(merged["price_level"].max(), merged["bigmac_level"].max())) * 1.05
        scatter.add_scatter(x=[0, top], y=[0, top], mode="lines", line=dict(dash="dash", color="#9ca3af"), name="Equal")
        scatter.update_xaxes(title_text="PPP / exchange rate x 100 (World Bank data)")
        scatter.update_yaxes(title_text="Big Mac price level (US = 100)")
        scatter.update_layout(hovermode="closest")
        st.plotly_chart(charts.theme(scatter, title=f"Two price levels, {year}"), width="stretch")
        st.caption(
            f"{stats['n']} countries in both. Spearman rank correlation {stats['spearman']:.2f}, Pearson {stats['pearson']:.2f}; "
            f"the Big Mac level is a median {stats['median_ratio']:.2f} times our broader price level (one traded good against a whole economy)."
        )

# --------------------------------------------------------------------------- income

with tab_income:
    if not picked:
        st.info("Pick countries in the sidebar.")
    else:
        inc = pp.income_table(panel, year, picked)
        if inc.empty:
            st.warning("No income data for the chosen countries in this year.")
        else:
            long = inc.melt(id_vars=["iso3", "country"], value_vars=["gdp_nominal", "gdp_ppp"], var_name="measure", value_name="value")
            long["measure"] = long["measure"].map({"gdp_nominal": "Nominal (US$ at market rates)", "gdp_ppp": "PPP (international $)"})
            fig = charts.bars(long, x="country", y="value", color="measure", barmode="group", title=f"GDP per head, {year}", yaxis_title="US$ / international $")
            st.plotly_chart(fig, width="stretch")
            shown = inc.drop(columns="iso3").rename(
                columns={"country": "Country", "gdp_nominal": "Nominal GDP per head", "gdp_ppp": "PPP GDP per head", "price_level": "Price level (US = 100)", "ppp_over_nominal": "PPP / nominal"}
            )
            st.dataframe(shown.round(2), hide_index=True, width="stretch")
            st.caption("PPP / nominal = 100 / price level: where prices are low, the same income buys more, so PPP income is higher than nominal income.")
            ui.download(shown.round(2), f"income_nominal_vs_ppp_{year}.csv")

# --------------------------------------------------------------------------- Penn effect

with tab_penn:
    income = st.radio("Income on the x-axis", ["gdp_ppp", "gdp_nominal"], format_func={"gdp_ppp": "GDP per head, PPP (standard)", "gdp_nominal": "GDP per head, nominal US$"}.get, horizontal=True, key="pp_income")
    sample = pp.penn_sample(panel, year, income)
    try:
        fit = pp.penn_fit(sample, income)
    except ValueError as err:
        st.warning(str(err))
    else:
        sample = sample.assign(region=region.reindex(sample.index).fillna("Other"))
        fig = go.Figure()
        for name, group in sample.groupby("region"):
            fig.add_scatter(x=group[income], y=group["price_level"], mode="markers", name=name, text=group["country"], marker=dict(size=8))
        grid = np.geomspace(sample[income].min(), sample[income].max(), 100)
        fig.add_scatter(x=grid, y=fit.predict(grid), mode="lines", name="Fitted line (statsmodels OLS)", line=dict(color="#111827", width=3))
        chosen = sample.loc[sample.index.intersection(picked)]
        fig.add_scatter(x=chosen[income], y=chosen["price_level"], mode="text", text=chosen["country"], textposition="top center", showlegend=False)
        fig.update_xaxes(type="log", title_text="GDP per head, PPP, international $ (log scale)" if income == "gdp_ppp" else "GDP per head, nominal US$ (log scale)")
        fig.update_yaxes(type="log", title_text="Price level, US = 100 (log scale)")
        fig.update_layout(hovermode="closest")
        st.plotly_chart(charts.theme(fig, title=f"Price level against income, {year}", height=560), width="stretch")
        lo, hi = fit.ci95
        a, b, c, d = st.columns(4)
        a.metric("Slope (elasticity)", f"{fit.slope:.3f}", help="Regression of ln(price level) on ln(income). Robust (HC1) standard errors.")
        b.metric("95% interval", f"{lo:.3f} to {hi:.3f}")
        c.metric("R-squared", f"{fit.r_squared:.2f}")
        d.metric("Countries", f"{fit.n}")
        st.caption(
            f"A 10% higher income goes with a {fit.ten_percent_effect:.1f}% higher price level (p = {fit.p_value:.1e}). "
            "This is the Penn effect, usually explained by the Balassa-Samuelson mechanism: productivity gaps are larger in traded goods than in services, "
            "so wages and the prices of non-traded services rise with income."
        )
        if income == "gdp_nominal":
            st.warning("Nominal income is built from the price level (nominal = PPP income x price level / 100), so this fit overstates the link. Use PPP income for the standard test.")
        yearly = pp.penn_by_year(panel, income, first_year=2000)
        trend = go.Figure()
        trend.add_scatter(x=yearly["year"], y=yearly["slope"], mode="lines+markers", name="Slope")
        trend.add_scatter(x=yearly["year"], y=yearly["slope"] + 1.96 * yearly["se"], mode="lines", line=dict(width=0), showlegend=False)
        trend.add_scatter(x=yearly["year"], y=yearly["slope"] - 1.96 * yearly["se"], mode="lines", line=dict(width=0), fill="tonexty", fillcolor="rgba(37,99,235,0.15)", name="95% interval")
        st.plotly_chart(charts.theme(trend, title="The fitted slope, year by year", yaxis_title="Elasticity"), width="stretch")
        ui.download(sample.reset_index()[["iso3", "country", "year", "price_level", income]], f"price_level_vs_income_{year}.csv")

ui.sources(
    "World Bank: PPP conversion factor, GDP `PA.NUS.PPP`; official exchange rate `PA.NUS.FCRF`; price level index `PA.NUS.GDP.PLI` (used to cross-check); GDP per capita `NY.GDP.PCAP.CD` and PPP `NY.GDP.PCAP.PP.CD`. CC BY 4.0.",
    "The Economist Big Mac index (CC BY): January and July releases, 54 economies, euro area excluded.",
    "Price level = PPP conversion factor / exchange rate x 100. Country-years where this disagrees with the World Bank's published index by more than 1 point (currency-unit mismatches, for example Bulgaria, Croatia, Liberia, Zimbabwe) are left out of the converter, the valuation chart and the regression.",
    "PPP factors come from International Comparison Program benchmark rounds and are extrapolated between them, so recent years are estimates. The Big Mac is one product and is not a general cost-of-living measure.",
)
