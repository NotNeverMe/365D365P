# 011 · National Debt Dashboard

> Which governments carry the most debt once you measure it against what they collect in revenue, not just against GDP?

## What it does
Compares central government debt across countries three ways: as a share of GDP, as years of government revenue, and through the interest bill as a share of revenue. A scatter of debt-to-GDP against debt-to-revenue shows why the two rankings differ, a coverage tab shows exactly which countries and years are missing, and a separate tab traces US federal debt back to 1966.

Every chart says how many countries it shows and lists the ones it leaves out, with the missing input. Nothing is dropped silently.

## Data

| Source | Series | What it measures | Coverage |
|---|---|---|---|
| World Bank (IMF GFS) | `GC.DOD.TOTL.GD.ZS` | Central government debt, % of GDP | 109 of 217 economies, 1970-2024 |
| World Bank (IMF GFS) | `GC.REV.XGRT.GD.ZS` | Revenue excluding grants, % of GDP | 162 economies, 1972-2024 |
| World Bank (IMF GFS) | `GC.XPN.INTP.ZS` | Interest payments, % of expense | 156 economies, 1972-2024 |
| World Bank (IMF GFS) | `GC.XPN.TOTL.GD.ZS` | Expense, % of GDP | 161 economies, 1972-2024 |
| World Bank (cross-check only) | `GC.XPN.INTP.RV.ZS` | Interest payments, % of revenue, as published | 160 economies, 1972-2024 |
| FRED | `GFDEGDQ188S` | US federal debt, gross (total public debt), % of GDP, quarterly | 1966-Q1 to 2026-Q1 |
| FRED | `FYGFGDQ188S` | US federal debt held by the public, % of GDP, quarterly | 1970-Q1 to 2026-Q1 |

World Bank data are CC BY 4.0; FRED series are public Federal Reserve Bank of St. Louis data. Downloads are cached under `data/` and committed.

## Method
All inputs describe the central government as a percentage of the same GDP, so GDP cancels out.

    debt_to_revenue     = debt (% GDP) / revenue excluding grants (% GDP)          in years of revenue
    interest_gdp        = interest share of expense (%) / 100 x expense (% GDP)    in % of GDP
    interest_to_revenue = interest_gdp / revenue (% GDP) x 100                     in % of revenue

* A ratio is built only from inputs of the **same year** for the same country. Revenue of zero or below is treated as missing.
* The ranking views use one year. The default is the latest year in which at least 75% of the peak number of countries report (2022 for debt-to-revenue; the newest years are too thin). An optional slider accepts figures up to five years older, and the data year is then shown on hover and in tables.
* Rank shift is `rank by debt-to-GDP - rank by debt-to-revenue` (1 = highest), so a positive shift means a country looks worse once revenue is the yardstick. The agreement between the two orderings is the Spearman rank correlation.
* **Validation.** The World Bank also publishes interest as a share of revenue. The derived series is compared with it for every country-year both exist.

## What the data say
Reproduce everything below with `python projects/011-national-debt-dashboard/national_debt.py`.

1. **The debt data cover half the world and miss famous cases.** Only 109 of 217 economies have a central government debt figure in any year. In 2022, 43 countries allow debt-to-revenue to be computed (peak 56 in 2019; 40 in 2023; 33 in 2024). Japan, France, China, Greece and Argentina have no debt figure in any year; Germany has 1990 only and Italy 1991-92. Interest-to-revenue is far wider, with 108 countries in 2022.
2. **Debt-to-GDP and debt-to-revenue tell different stories.** Across the 43 countries of 2022 the two orderings have a Spearman correlation of 0.76: related, not equal. Somalia owed 43.4% of GDP (32nd of 43) but collected only 2.6% of GDP, so its debt is 16.8 years of revenue (1st). Uganda moves from 24th to 7th (53.9% of GDP; 3.9 years). At the other end, Hungary has debt of 78.0% of GDP (9th) but revenue of 37.9% of GDP, so 2.1 years of revenue (26th), and San Marino drops from 5th to 23rd. The United Kingdom (138.2% of GDP, 2nd) is 8th at 3.9 years; the United States is 3rd on both (112.7% of GDP, 5.7 years) because federal revenue is only 19.9% of GDP.
3. **Singapore tops the debt-to-GDP list (152.5%) and is 2nd on debt-to-revenue (9.7 years).** Singapore's [Ministry of Finance](https://www.mof.gov.sg/policies/reserves/our-assets-and-liabilities/) states that the government does not borrow for recurrent spending, so a high ratio here is not a sign of fiscal strain. This is a reminder that the ratios describe size, not distress.
4. **Interest burdens are concentrated in a few stressed budgets.** In 2022 Sri Lanka spent 79.1% of revenue on interest, Ghana 47.8%, Malawi 37.6%, India 34.0% and Brazil 28.9%. The median among 108 countries was 4.9%.
5. **US federal debt reached 132.7% of GDP in 2020-Q2** (gross, FRED), up from a low of 30.6% in 1981-Q3 and 122.6% in 2026-Q1. Held by the public, the range is 21.9% (1974-Q3) to 103.0% (2020-Q2), now 98.7%. The World Bank's US figure follows the publicly held measure in 2000 (33.3% against 34.3%) but is closer to gross debt by 2022 (112.7% against 118.4% gross and 92.8% held by the public).
6. **The derived interest-to-revenue formula checks out.** Against the World Bank's own series it is within one point in 88.7% of 4,263 country-years (median gap 0.05 points, correlation 0.996). Where the two differ by more than a point (483 cases), the derived figure is the higher one in 99.8%, consistent with the published series using a larger revenue denominator such as revenue including grants. I did not confirm that cause.

## Limits
* **Patchy coverage is the main limit.** Rankings only include countries that report, and the set changes year to year, so a country's rank can move because others enter or leave the sample. The coverage tab lists every country and the years available.
* **Central government only.** Subnational and social security debt are excluded, which matters for federal countries.
* **Definitions are not uniform.** The World Bank series does not say whether debt is gross or net, or whether intragovernmental holdings count, and the US example above shows the basis can differ between years. Revenue excludes grants, which lowers revenue and raises ratios for aid-dependent states.
* **Small denominators inflate ratios.** Somalia's 16.8 years rests on revenue of 2.6% of GDP.
* **Debt-to-revenue is not a solvency test.** It ignores interest rates, maturity, currency and assets. The 2022 sample is also skewed to countries that report, not to the world's largest debtors.
* The derived interest-to-revenue is built from three series with possibly different bases and can differ from the published figure (see finding 6).

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/011-national-debt-dashboard/app.py
    pytest projects/011-national-debt-dashboard
