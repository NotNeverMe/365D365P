# 005 · Cost of Living Index

> What does the same basket of everyday goods and services cost in one place compared with another, and what salary would keep your purchasing power if you moved?

**Read this first: there is no open, reusable city-level price dataset for the world.** I looked for one (see Data) and found genuine city-level data only for **US metropolitan areas**. Everything outside the US is **country-level**: a country figure is an average for the whole economy and says nothing about any single city, capital or otherwise. The app and this README keep the two parts apart and never label a country figure as a city.

## What it does
Two tabs. **US metro areas** compares 387 metropolitan areas (2008-2024): pick two, enter a salary, and see the equivalent salary plus a breakdown into goods, housing, utilities and other services. **Countries** does the same at country level with three measures (World Bank household consumption, World Bank whole economy, and the Big Mac). Each tab has a ranked table of the most and least expensive places and a chart of how the price level has changed over time.

## Data
| Part | Source | Series | Coverage | Licence |
|---|---|---|---|---|
| US metro areas | U.S. Bureau of Economic Analysis, Regional Price Parities by MSA (table `MARPP`) | RPPs: all items, goods, housing, utilities, other services; US average = 100 | 387 metropolitan statistical areas, 2008-2024 (a few start later: Enid OK 2013, Twin Falls ID 2015, Kiryas Joel-Poughkeepsie-Newburgh NY 2016) | US government data, public domain; BEA asks for attribution |
| Countries | World Bank, International Comparison Program | `PA.NUS.PRVT.PLI` price level index, household consumption (US = 100); `PA.NUS.GDP.PLI` price level index, GDP | 1990-2025; 208 economies appear at some point, at most 206 in a year (164 with a household value in 2025) | CC BY 4.0 |
| Countries | The Economist Big Mac index (`core.bigmac`) | Dollar price of a Big Mac relative to the US price, rebased to US = 100 | 53 economies in 2025 (euro area dropped: it is not a country) | CC BY |

The brief suggested `PA.NUS.PPPC.RF`; the World Bank API no longer has it ("indicator not found"). Its successors `PA.NUS.PRVT.PLI` and `PA.NUS.GDP.PLI` are the same idea (PPP conversion factor over market exchange rate, US = 100) and are what the app uses.

**How I searched for city data.** Free worldwide city price tables (including the Kaggle copies) are scraped from Numbeo, whose terms prohibit scraping and say public redistribution needs prior consent, with no open licence. Mercer, UBS and the Economist Intelligence Unit are proprietary. The BEA file is hosted on `apps.bea.gov`, is reachable, and BEA states its data are in the public domain and may be reused without permission. It is the only clearly open city-level source I found, and it covers the US only.

## Method
**What each index measures.**
* **BEA regional price parity (RPP)**: the price level of a metropolitan area relative to the US as a whole *in the same year*, 100 = US average. 110 means that area's basket costs 10% more than the US average. BEA builds it from Consumer Price Index survey data for goods and services and from American Community Survey data for housing rents, with expenditure weights from its state-level consumption series. "All items" combines the four components. Because every year is rebased to that year's US average, an RPP is a *relative* price level, not inflation, and its change over time only says whether a place got dearer or cheaper than the US overall.
* **World Bank price level index, household consumption**: the PPP conversion factor for household consumption divided by the market exchange rate, times 100, so the United States is 100 by construction. Where a country has 50, a dollar converted at market rates buys about twice as much of a comparable household basket as in the US. The PPP factors come from International Comparison Program surveys of comparable items, and values between benchmark rounds are extrapolated. The GDP version covers all final expenditure, including government and investment.
* **Big Mac price level**: one product, the Big Mac's dollar price over the US price. It is a single traded good with local labour and rent embedded, so it is easy to read but narrow.

**Equivalent salary.** If A and B have price indices *p_A* and *p_B*, a salary *s* in A matches *s × p_B / p_A* in B. The metro version is in dollars (all metros share a currency); the country version is in US dollars at market exchange rates. It keeps purchasing power over the *index basket* fixed, which is not the same as keeping your own lifestyle fixed.

## What the data say
Reproduce with `python projects/005-cost-of-living-index/cost_of_living.py`.

1. **Within the US, housing is what makes places expensive.** In 2024 the all-items index runs from 83.6 (Monroe LA) to 115.6 (San Francisco). Across metros, the 10th-to-90th percentile range of the housing index is 64.4 points against 11.5 for goods and 5.0 for other services, and housing correlates 0.94 with the all-items index.
2. **A move from New York to Dallas** (2024: 112.6 against 103.1) means USD 100,000 in New York matches about USD 91,584 in Dallas, 8.4% less. The gap is mostly housing (148.6 against 117.9, 20.7% less) and utilities (127.0 against 90.7). Jackson, MS (a much cheaper area) matches USD 79,109.
3. **Across countries the spread is far larger.** In 2025 the household price level runs from 15.6 (Egypt) through 22.7 (India) up to 128.2 (Switzerland) and 129.7 (Iceland). USD 100,000 earned in the US matches USD 81,233 in Germany, USD 128,169 in Switzerland and USD 22,718 in India at market exchange rates.
4. **The Big Mac and the World Bank agree on the order but not the level.** Across the 48 countries with both in 2025 the rank correlation is 0.74 (Pearson 0.77), and the Big Mac price level is a median 1.40 times the World Bank household price level, which is consistent with the Big Mac carrying more traded-goods content than a household basket heavy in cheap local services.
5. **Relative price levels move a lot.** Between 2010 and 2025 Japan's household price level fell from 137.9 to 69.0 and Norway's from 161.6 to 96.2 (both relative to the US, driven largely by exchange rates). Within the US, from 2008 to 2024 the Atlantic City NJ index fell from 110.7 to 98.9 while Great Falls MT's rose from 85.3 to 96.8.

## Limits
* **No city-level data outside the US.** Country figures are national averages. Living costs in Zurich or Lagos can differ a lot from Switzerland's or Nigeria's, and nothing here tells you by how much.
* **Metro areas are not cities.** A BEA metropolitan statistical area is a whole labour-market region (for example "New York-Newark-Jersey City, NY-NJ"), not city limits, and it can include cheap suburbs.
* **A price index is not a budget.** It prices an average basket. It leaves out income taxes, wages, quality, and what you personally buy. The metro RPPs use national expenditure weights, so they will not match a household that spends unusually on housing.
* **Cross-year comparisons are of relative position only.** BEA RPPs measure differences at one point in time; the app's time chart shows each place against that year's US average, not price inflation.
* **Exchange rates distort country figures.** Where official rates lag domestic inflation the index can be implausible: Haiti is ranked 5th most expensive in 2025 at 102.2 (above Germany's 81.2), up from 50.1 in 2010. The World Bank also extrapolates between International Comparison Program benchmark years, so recent values are estimates.
* **Coverage differs by measure.** In 2025 the household index covers 164 countries, the GDP index 185 and the Big Mac 53, mostly richer and middle-income economies.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/005-cost-of-living-index/app.py
    pytest projects/005-cost-of-living-index
