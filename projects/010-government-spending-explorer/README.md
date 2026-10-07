# 010 · Government Spending Explorer

> What do governments spend money on, and how does that differ across countries and over time?

## What it does
Pick a country and year to see its spending split two ways: by **function** (education, health, military, plus the full ten-division COFOG split for 30 European countries) and by **economic category** (pay, goods and services, interest, subsidies and transfers, other). Further views show trends over time, a cross-country ranking of any series, and the countries where interest payments take the largest share of the budget.

The two splits use different denominators and different levels of government. The app shows them in separate charts and never adds them together.

## Data

| Source | Series | What it measures | Coverage |
|---|---|---|---|
| World Bank (IMF GFS) | `GC.XPN.TOTL.GD.ZS` | Total expense, **% of GDP**, central government | 161 countries, 1972-2024 |
| World Bank (UNESCO) | `SE.XPD.TOTL.GD.ZS` | Education spending, **% of GDP**, general government | 203 countries, 1970-2025 |
| World Bank (WHO) | `SH.XPD.GHED.GD.ZS` | Government-funded health spending, **% of GDP** | 193 countries, 2000-2024 |
| World Bank (SIPRI) | `MS.MIL.XPND.GD.ZS` | Military spending, **% of GDP** | 164 countries, 1960-2024 |
| World Bank (IMF GFS) | `GC.XPN.COMP.ZS`, `GC.XPN.GSRV.ZS`, `GC.XPN.INTP.ZS`, `GC.XPN.TRFT.ZS`, `GC.XPN.OTHR.ZS` | Compensation of employees, goods and services, interest, subsidies and other transfers, other expense: each **% of total central government expense** | 152-157 countries each, 1972-2024 (other expense from 1990) |
| Eurostat `gov_10a_exp` | COFOG divisions GF01-GF10 | General government expenditure by function, % of GDP and % of total expenditure | 30 European countries, 1990-2025 (27 start in 1995) |

All World Bank codes were checked against the API before use. The Eurostat file is downloaded once by `load_cofog()` and cached in `data/eurostat/`. Both sources allow reuse with attribution (World Bank: CC BY 4.0; Eurostat: Commission reuse policy).

## Method
* **Function view** (`% of GDP`): three World Bank series, each reported as published. The "Total expense" figure is shown only as context, because it covers central government while education and health cover general government.
* **Economic view** (`% of total expense`): the five reported shares. Where all five exist they add to 100 (checked below). An optional conversion to % of GDP uses `share x expense / 100`, which is valid because both numbers describe the same central government.
* **Snapshot for a country and year**: the app takes the latest observation on or before the chosen year within a window you set (0 to 5 years). The year of every value is shown in the table, and series with nothing in the window are listed as missing. Nothing is interpolated.
* **Interest ranking**: countries sorted by interest as a share of expense in one year. The same bill expressed as % of GDP (`share x expense / 100`) is shown beside it, because a small budget can make a modest bill look large as a share.
* **COFOG**: the ten first-level divisions of Eurostat's table, with the two units (% of GDP, % of total expenditure) kept in separate columns.

## What the data say
Reproduce everything below with `python projects/010-government-spending-explorer/gov_spending.py`.

1. **Interest takes the largest budget share in countries in debt stress.** In 2022 (108 countries report, the latest year with more than 100), Sri Lanka spent 41.3% of central government expense on interest (6.5% of GDP), Ghana 32.8% (7.4% of GDP), Malawi 26.3%, Brazil 24.6% (7.8% of GDP, the largest bill relative to GDP in the top ten) and India 23.2%. The median country spent 5.2%.
2. **Scope changes the answer.** Germany's central government expense was 31.2% of GDP in 2022, while Eurostat's general government total was 48.6% (ratio 0.64). France: 48.9% against 58.4%. Across the 30 countries in both sources the median ratio of central to general is 0.87. This is why function and economic series from different sources are not combined.
3. **Transfers dominate the typical budget.** In 2022 the median country spent 42.5% of central government expense on subsidies and other transfers, 20.9% on staff, 12.7% on goods and services, 7.5% on other items and 5.2% on interest. The US federal budget that year was 24.6% of GDP, of which transfers were 16.7 points and interest 2.7.
4. **Social protection is the largest function in Europe.** Across 30 European countries in 2024 it averaged 36.4% of total expenditure, then health 14.9%, general public services 12.2%, economic affairs 11.6%, education 11.3% and defence 3.4%. Germany spent 20.4% of GDP on social protection (41.3% of its expenditure).
5. **The economic shares are internally consistent.** Of 3,086 country-years with all five reported, 82.9% add to 100 within one point (median sum 100.00).

## Limits
* **No global COFOG.** Outside Europe the data only give education, health and military by function. Eurostat was the only reachable open source with the full classification; OECD and IMF SDMX endpoints also answer from the sandbox but were not used. A country outside the 30 European ones has no ten-division split.
* **Mixed scope.** Total expense and the economic shares are central government. Education and health are general government. Military follows SIPRI's definition. Do not subtract one from another.
* **Central government hides most of federal countries' spending.** Germany's central expense is 64% of its general government total, so shares of "expense" are not shares of all public spending.
* **Gaps in large economies.** China, Indonesia, Japan and Russia have no interest-payment figure for 2022. Japan and China have no economic-category data in any year (China has no central government expense figure either); Indonesia's series stops in 2009 and Russia's in 2020. Coverage also falls sharply after 2022 (about 85 countries in 2023, one in 2024).
* **Outliers are real but small economies.** For example Kiribati's total expense is 81.5% of GDP (2022) and Ukraine's military spending is 34.5% of GDP (2024). Medians are quoted instead of means.
* **Classification varies by country.** "Other expense" and "subsidies and other transfers" are broad, and in 17% of country-years the five shares do not add to 100 within a point.
* Eurostat values flagged as provisional (`p`, about 3% of rows) are included and kept in the cached file.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/010-government-spending-explorer/app.py
    pytest projects/010-government-spending-explorer
