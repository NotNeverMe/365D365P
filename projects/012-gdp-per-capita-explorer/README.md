# 012 · GDP per Capita Explorer

> How closely do living standards track income, are poorer countries catching up, and is the world's income distribution becoming more equal?

## What it does
Four views of cross-country living standards. A year slider drives a bubble chart of log income against life expectancy (the Preston curve) with a fitted curve and its coefficients. A comparison table lines up income, health, population, emissions and electricity use for chosen countries. A convergence test asks whether poorer countries grew faster, over any window you choose. A last tab traces the population-weighted Gini of average incomes across countries, and lets you leave countries out to see how much they explain.

## Data

| Source | Series | What it measures | Coverage |
|---|---|---|---|
| World Bank (ICP) | `NY.GDP.PCAP.PP.KD` | GDP per capita, PPP, constant 2021 international $ | 199 economies, 1990-2025 |
| World Bank | `NY.GDP.PCAP.CD` | GDP per capita, current US$ | 214 economies, 1960-2025 |
| World Bank (UN WPP) | `SP.DYN.LE00.IN` | Life expectancy at birth | 217 economies, 1960-2024 |
| World Bank (UN IGME) | `SP.DYN.IMRT.IN` | Infant mortality per 1,000 live births | 196 economies, 1960-2024 |
| World Bank (UN WPP) | `SP.POP.TOTL` | Population | 217 economies, 1960-2025 |
| World Bank (EDGAR) | `EN.GHG.CO2.PC.CE.AR5` | CO2 emissions excluding land use, t CO2e per person | 203 economies, 1970-2024 |
| World Bank (IEA) | `EG.USE.ELEC.KH.PC` | Electric power consumption, kWh per person | 150 economies, 1990-2024 (41 in 2024) |

`EN.ATM.CO2E.PC`, the older per-capita CO2 series, no longer exists in the World Bank API (indicator archived), so the EDGAR series is used. Data are CC BY 4.0 and cached under `data/`.

## Method
* **Preston curve.** For one year, OLS across countries of `life expectancy = a + b * ln(GDP per capita, PPP)`, one observation per country, with heteroskedasticity-robust (HC1) standard errors. `b` is years of life expectancy per log point of income, so doubling income goes with `b * ln 2` more years. A checkbox adds `ln(income)^2` to test curvature. This describes an association; it does not show that income causes longevity.
* **Absolute beta-convergence.** For a window `[start, end]`, average annual log growth of GDP per capita (PPP, in % per year) is regressed on `ln(income in start)`: `growth = a + beta * ln(y_start)`, robust standard errors, countries with income in both years. **What the sign means:** `beta < 0` means countries that started poorer grew faster, so incomes converge; `beta > 0` means richer countries grew faster (divergence); `beta` near zero means initial income says nothing about growth. A `beta` of -0.4 means a country that started with half the income grew about 0.27 percentage points per year faster (`0.4 * ln 2`). Options restrict to countries above a population size or weight by starting population. The implied half-life of the income gap comes from `lambda = -ln(1 + beta * T / 100) / T` (Barro and Sala-i-Martin), `T` being the window length.
* **Weighted Gini.** For each year, `core.inequality.gini` on countries' PPP income per head with population as weights. This gives each person their country's average income, so it measures inequality *between* countries, not within them. The unweighted version, treating each country as one observation, is shown alongside. Coverage (share of population with an income figure) is reported for every year.
* **Years used.** The default "latest year" is the latest with at least 95% of each series' peak country count (2024 for income, life expectancy and population; 2023 once electricity is included).

## What the data say
Reproduce everything below with `python projects/012-gdp-per-capita-explorer/gdp_per_capita.py`.

1. **Income and life expectancy move together, but the curve has shifted and flattened.** In 2024, across 195 countries, `life expectancy = 22.85 + 5.26 x ln(income)`: slope standard error 0.21, R-squared 0.744, so doubling income goes with 3.6 more years. In 1990 (185 countries) it was `6.23 + 6.44 x ln(income)` (slope se 0.39, R-squared 0.636), or 4.5 years per doubling. At $5,000 of income the fit predicts 61.1 years in 1990 and 67.6 in 2024, 6.5 years more at the same income. The curvature term was significant in 1990 (-0.80, p = 0.004) and not in 2024 (0.18, p = 0.31).
2. **Income does not settle living standards.** In 2023, Nigeria's income per head ($7,843 PPP) is 88% of India's ($8,871), yet life expectancy is 54.5 against 72.0 years and infant mortality 70.1 against 24.5 per 1,000. China ($22,687) has life expectancy of 78.0 years, within half a year of the United States (78.4) at $74,352.
3. **Poorer countries have grown faster, weakly, and only after 2000.** Over 1990-2024, `beta = -0.395` (standard error 0.108, p = 0.0002, n = 183 countries, R-squared 0.086). That implies a half-life of the income gap of about 163 years. Limiting to the 139 countries with at least 1 million people gives -0.309 (se 0.120). Weighting by population, which gives China and India their weight, gives -1.546 (se 0.436, R-squared 0.513, half-life 32 years). By sub-period: 1990-2000 -0.340 (se 0.270, p = 0.21, not significant), 2000-2010 -0.524 (se 0.137, p < 0.001), 2010-2024 -0.307 (se 0.110, p = 0.005).
4. **Between-country inequality fell sharply, mostly because of China.** The population-weighted Gini of GDP per capita (PPP) was 0.609 in 1990 (185 countries, 98.0% of world population) and 0.455 in 2024 (195 countries, 98.2%). Unweighted it moved from 0.555 to 0.508. Leaving out China, the weighted Gini goes from 0.557 to 0.503; leaving out China and India, from 0.491 to 0.505, so it does not fall.

## Limits
* **Cross-country averages.** All three results treat a country as its mean income. Inequality within countries is outside the Gini and the convergence test.
* **PPP income only starts in 1990** and uses the 2021 price base, so longer comparisons are not possible with this series. The latest year is 2024; 2025 has fewer countries.
* **Absolute convergence is an unconditional test.** It does not control for institutions, schooling, investment or resource wealth. Small, resource-rich or conflict-affected economies (for example Guyana and Equatorial Guinea are among the fastest growers) strongly influence an unweighted fit, which is why the population-restricted and weighted versions are reported.
* **R-squared is low in the convergence test** (0.086): initial income explains little of the variation in growth.
* **The Preston fit uses one observation per country**, not population weights, so small countries count as much as India and China.
* **Gaps stay gaps.** Electricity data end in 2023 for most countries (41 countries in 2024), infant mortality covers 196 economies and PPP income 199. Blank cells in the comparison table mean the source has no value.
* Life expectancy and population come from UN estimates and projections, not registers, for many low-income countries.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/012-gdp-per-capita-explorer/app.py
    pytest projects/012-gdp-per-capita-explorer
