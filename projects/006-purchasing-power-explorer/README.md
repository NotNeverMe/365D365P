# 006 · Purchasing Power Explorer

> How much can a currency actually buy at home, compared with what its exchange rate says, and does that gap follow national income?

## What it does
Four tabs. A **converter** shows what US$100 (or any amount) is worth in a chosen country at the market exchange rate and at purchasing power parity (PPP), with a Big Mac count as a sanity check. An **over/undervaluation** chart ranks currencies against the dollar using the Big Mac index (raw or GDP-adjusted) or the World Bank price level, with a scatter that checks the two against each other. An **income** tab sets nominal against PPP income per head, and a **price level vs income** tab plots the Penn effect with a fitted regression line and its slope.

## Data
| Source | Series | Coverage | Licence |
|---|---|---|---|
| World Bank | `PA.NUS.PPP` PPP conversion factor, GDP (local currency units per international $) | 205 economies, 1990-2025 | CC BY 4.0 |
| World Bank | `PA.NUS.FCRF` official exchange rate (local currency units per US$, period average) | 214 economies, 1960-2025 | CC BY 4.0 |
| World Bank | `PA.NUS.GDP.PLI` price level index, GDP (US = 100); used only to cross-check my own calculation | 204 economies, 1990-2025 | CC BY 4.0 |
| World Bank | `NY.GDP.PCAP.CD` GDP per head, current US$; `NY.GDP.PCAP.PP.CD` GDP per head, PPP, current international $ | 214 / 203 economies | CC BY 4.0 |
| The Economist, via `core.bigmac` | Big Mac dollar price, `USD_raw` and GDP-adjusted `USD_adjusted` over/undervaluation; January and July releases | 55 economies (53 in July 2026), April 2000 to July 2026, euro area excluded | CC BY |

The guide lists `PA.NUS.PPPC.RF` for price levels. It no longer exists in the World Bank API (it returns "indicator not found"), so I compute the price level myself from `PA.NUS.PPP` and `PA.NUS.FCRF`, and use `PA.NUS.GDP.PLI` as the published benchmark.

## Method
* **Price level index** = PPP conversion factor / official exchange rate × 100, with the United States at 100 (its PPP factor and exchange rate are both 1). Below 100, a dollar converted at market rates buys more at home than in the US. The matching over/undervaluation is price level / 100 − 1.
* **Quality filter.** A country-year is used only if my price level is within 1 point of the World Bank's published index. Where it is not, the PPP factor and the exchange rate are usually in different currency units, so their ratio is meaningless. Those rows are excluded from the converter, valuation chart and regression, and counted in the numbers below.
* **Converter.** For an amount *A* in dollars, *fx* local units per dollar and *ppp* local units per international dollar: at market rates *A* becomes *A × fx* local units. *A × ppp* local units buys what *A* dollars buys in the US. So *A × fx* units buys goods that cost *A × fx / ppp* dollars at US prices, a multiplier of 100 / price level.
* **Big Mac price level** = a country's dollar price over the US dollar price in the same release, × 100. That equals 100 × (1 + `USD_raw`), which the tests check. For cross-checks the January and July releases are averaged within a calendar year.
* **Penn effect.** OLS of ln(price level) on ln(GDP per head, PPP) across countries in one year, with heteroskedasticity-robust (HC1) standard errors, run with `statsmodels`. The slope is an elasticity. PPP income is the standard x variable; nominal income is itself price level × PPP income / 100, so regressing price level on it builds in part of the relationship.

## What the data say
Reproduce everything with `python projects/006-purchasing-power-explorer/purchasing_power.py`. The year is 2024, the latest with at least 90% of peak coverage.

1. **My price level matches the World Bank's for most country-years, and the mismatches are currency-unit gaps.** 88.4% of 6,723 country-years agree within 1 point. The most frequent exceptions are Bulgaria (35 years), Liberia (35), Croatia (31), Australia (29) and Naoero (27). For Bulgaria the published index is a median 1.96 times mine and for Croatia 7.53, which are the lev and kuna rates per euro: their PPP factors are in euros while the exchange rate is in national currency.
2. **US$100 buys very different amounts.** In India, US$100 becomes 8,367 rupees at the market rate, but 2,045 rupees buys what US$100 buys in the US: the price level is 24.4, so the dollars buy what US$409 buys in the US (×4.09). The multiplier is ×2.04 in China (price level 49.0), ×1.32 in Germany (75.9) and ×0.90 in Switzerland (110.5).
3. **PPP income can be several times nominal income.** In 2024 India's GDP per head is US$2,592 nominal and 10,719 PPP dollars (ratio 4.14); Nigeria's ratio is 8.39. Switzerland is the reverse, US$107,702 nominal against 97,468 PPP (0.90). The identity PPP income / nominal income = 100 / price level holds within 1% for 98.9% of the 174 consistent countries.
4. **The Big Mac agrees on the order, not the level.** In 2024, 50 countries have both measures: Spearman 0.69, Pearson 0.70, and the Big Mac price level is a median 1.49 times mine. The yearly rank correlation ranges from 0.65 to 0.84 across 2005-2024 (mean 0.76). In the July 2026 release the raw index has Indonesia (−62%), Taiwan (−61%) and India (−61%) most undervalued and Switzerland (+45%), Uruguay (+44%) and Norway (+29%) most overvalued; the GDP-adjusted index puts Uruguay at +77%, Colombia +64% and Switzerland +49%.
5. **The Penn effect is real but modest.** For 2024, across 174 countries, the slope of ln(price level) on ln(PPP income) is **0.196** (HC1 s.e. 0.025, 95% interval 0.146 to 0.246, R² 0.264, p = 1.5e-14): 10% higher income goes with a 1.9% higher price level. The fitted price level is 30 at 2,000 PPP dollars per head, 48 at 20,000 and 59 at 60,000. The slope is positive and significant in every year from 2000 to 2024, from 0.177 (2012) to 0.243 (2000). Using nominal income instead gives 0.222 and an R² of 0.521, which overstates the link for the reason above.

## Limits
* **PPP is an average over the whole economy's output,** not the basket of a tourist or a student. The Big Mac prices one product, so it is a vivid check and not a cost-of-living measure.
* **PPP factors are extrapolated.** They come from International Comparison Program benchmark rounds and are carried between them with relative inflation, so recent years are estimates and the series can be revised. 2025 has fewer countries (161 with a price level), which is why the app defaults to 2024.
* **Excluded countries.** The quality filter drops 8 countries from the 2024 regression, so the price-level analysis does not cover them. The official exchange rate is used even where it differs from the rate people trade at: Nigeria's 2024 price level is 11.9, the lowest of the 174 consistent economies (next: Lao PDR 21.7), probably reflecting the sharp fall of the official naira rate.
* **The regression is a correlation across countries,** not evidence about what causes price levels, and income explains only about a quarter of their variation (R² 0.26). The Balassa-Samuelson story is the standard explanation, but the data here do not test it.
* **Timing differs.** The World Bank uses annual averages; the Big Mac is priced in two months a year. The euro area aggregate is excluded and Taiwan appears only in the Big Mac data, so neither enters the cross-check.
* The converter reports local currency units without naming the currency, because the World Bank series do not carry currency codes.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/006-purchasing-power-explorer/app.py
    pytest projects/006-purchasing-power-explorer
