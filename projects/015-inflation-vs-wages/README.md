# 015 · Inflation vs Wages

> Have US wages kept pace with consumer prices, when did prices outrun pay, and do other rich countries look the same?

## What it does
Choose one of three US wage series, a window and a base month. The app plots nominal wages, prices and the real wage on one index, 12-month inflation against 12-month wage growth with the episodes in which prices outran wages shaded, the gap by calendar year, and the cross-correlation between wage growth and inflation at lags in both directions. Tables list the episodes and a decade summary. A second section compares real hourly earnings in manufacturing across OECD countries and lists every country that was dropped, with the reason.

## Data
Cached under `data/`; "last" means the last observation in the cached file.

| Source | Series | Coverage | Licence |
|---|---|---|---|
| FRED (`core.fred`) | `CPIAUCSL` CPI-U, all items, seasonally adjusted | 1947-01 to 2026-08. **One hole: 2025-10** (no October 2025 CPI was published) | public (BLS) |
| FRED | `AHETPI` average hourly earnings, production and nonsupervisory employees | 1964-01 to 2026-09, no gaps | public (BLS) |
| FRED | `CES0500000003` average hourly earnings, all private employees | 2006-03 to 2026-09 | public (BLS) |
| FRED | `LEU0252881500Q` median usual weekly earnings, full-time, nominal | 1979Q1 to 2026Q2; 2025Q4 missing | public (BLS) |
| FRED | `LES1252881600Q` the same, BLS real version (used only to check my deflation) | same | public (BLS) |
| FRED, from the OECD | `LCEAMN01<ISO2>…661S/N` hourly earnings in manufacturing, index 2015 = 100 | 31 countries; last observation between 2023-10 and 2026-07, median 2026-01 | OECD terms of use apply |
| World Bank (`core.worldbank`) | `FP.CPI.TOTL.ZG` CPI inflation, annual average % | prices for the panel; no US value for 2025, so the US uses annual averages of `CPIAUCSL` | CC BY 4.0 |

The id form suggested in the brief, `LCEAMN01xxM189S`, exists only for the United States (last 2023-11) and Canada (last 2023-09) among the countries I tried. The `…661S` and `…661N` index variants are current, so those are used. The OECD's matching CPI-growth series on FRED (`CPALTT01<ISO2>M659N`, quarterly `Q659N` for Australia and New Zealand) are stale, which is why prices come from the World Bank: across the 31 panel countries their last observation ranges from 2021-06 (Japan) to 2025-04, median 2025-03, and none reaches 2025-12.

## Method
* **Alignment.** A monthly wage series is paired with the CPI of the same month. A quarterly wage series is paired with the average CPI of its three months (as BLS does); quarters with fewer than three CPI readings are dropped. My deflation of the median weekly series differs from BLS's own real series by 0.62% on average and 1.62% at most across 189 quarters (BLS rounds to whole dollars).
* **Real wage** = nominal wage / CPI * 100, in 1982-84 dollars. **Cumulative real change** from a base month is `real_t / real_base - 1` (the first observation on or after the base). **12-month real growth** is `(1 + wage growth) / (1 + inflation) - 1`.
* **Share of months with falling real wages** is the share of months whose 12-month real growth is below zero (month-over-month is also reported, but it is noisy).
* **Episodes where prices outran wages.** A maximal run of consecutive months in which 12-month CPI inflation exceeds 12-month wage growth; runs shorter than six months are not listed. The gap is inflation minus wage growth in percentage points, reported as the run's mean and peak.
* **Decade summary.** Compound annual rates between a decade's endpoints (from the last observation of the previous decade), not averages of annual rates.
* **Lead/lag.** `statsmodels.tsa.stattools.ccf` on 12-month rates. The value at lag k is the correlation of wage growth at t+k with inflation at t, so a peak at positive k means wages follow prices. The peak is the highest correlation; the plateau is the run of lags within 0.02 of it.
* **The missing October 2025 CPI.** Growth over "12 months" is computed on calendar dates, not row counts, so the hole cannot shift later comparisons by a month; episodes cannot run across it; and `ccf`, which needs an unbroken series, uses the longest unbroken stretch (this drops the final ten months for the 2020-2026 window, leaving 69).
* **Panel.** For each country: annual average of the wage index, its growth, and real growth `(1 + wage) / (1 + inflation) - 1`, compounded from a base year. A country is included only if its wage index has complete annual averages for every year from the base year to the last year and prices exist for every year after the base year; otherwise it is dropped and the reason recorded.

## What the data say
Reproduce everything below with `python projects/015-inflation-vs-wages/inflation_wages.py`.

1. **Real wages are higher than before the 2021-22 inflation, but the answer depends on the base and the series.** Using `AHETPI`, the real wage is 6.3% above January 2019 (to August 2026), 5.5% above January 2020, but only 1.6% above January 2021 and 0.8% below its April 2020 peak. April 2020 itself is a jump of 5.9% in two months, which is widely attributed to low-paid workers losing jobs first (composition) rather than to pay rises. From January 2019 the other measures give +3.4% (`CES0500000003`, all private employees, to 2026-08) and +5.2% (median weekly earnings, to 2026Q2).
2. **Over the long run, gains are small.** Between January 1964 and August 2026 the `AHETPI` real wage rose 20.5%, over 62 years and 7 months. It was 5.8% below its 1964 level in April 1995 and is only 3.2% above January 1973.
3. **Real wages fall in a large minority of months.** On a 12-month basis, 40.6% of the 739 `AHETPI` months since 1965 had falling real wages (41.5% of 511 since 1983); month-over-month the share is 45.3%. For `CES0500000003` (2006 onward) it is 29.6% of 233 months, and for median weekly earnings 44.3% of 185 quarters.
4. **Prices outran wages in ten long episodes.** With `AHETPI` and a six-month minimum, the ten episodes cover 266 of 739 months. The worst ran from 1978-09 to 1982-08 (48 months, mean gap 2.81 pp, peak 7.04 pp in 1980-03 when inflation was 14.59% and wage growth 7.56%), followed by 1973-08 to 1976-03 (peak 4.42 pp in 1974-11). The longest was 1987-03 to 1993-12 (82 months) but shallow (mean gap 0.95 pp). The latest ran from 2021-11 to 2023-02 (16 months, mean 1.38 pp, peak 2.40 pp in 2022-06 with inflation 8.98% and wage growth 6.58%). On annual averages, inflation exceeded wage growth in 25 of 60 calendar years (1965-2024); 2022 (+1.6 pp) is the only such year since 2012.
5. **Decades, compound annual rates (%), `AHETPI`:**

   | Decade | Inflation | Wage growth | Real wage growth | Months with falling real wage |
   |---|---|---|---|---|
   | 1960s (from 1964-01) | 3.40 | 4.86 | +1.41 | 0% |
   | 1970s | 7.39 | 7.08 | -0.29 | 46% |
   | 1980s | 5.09 | 4.28 | -0.76 | 78% |
   | 1990s | 2.94 | 3.22 | +0.27 | 49% |
   | 2000s | 2.56 | 3.24 | +0.66 | 34% |
   | 2010s | 1.75 | 2.39 | +0.62 | 22% |
   | 2020s (to 2026-08) | 3.92 | 4.77 | +0.82 | 32% |

6. **Wages follow prices by months, but the lag is weakly identified.** On 12-month rates the peak is at lag +3 months (r = 0.39) for 1983-2019, with the plateau spanning lags 0 to +6; at lag 0 (r = 0.72) for 1964-82; and at +2 months (r = 0.56) for 2020-26 (69 months). The full sample peaks at +1 with r = 0.77 and a plateau from -6 to +5. On month-over-month changes there is no stable peak (-3 months, r = 0.32, full sample; +5, r = 0.14, for 1983-2019), and on monthly changes of the 12-month rate the peak jumps between -26 and +6 months with r no higher than 0.28. The strong correlations on 12-month rates mostly reflect that both series are persistent.
7. **Cross-country panel.** With base 2019 and last year 2025, 25 of 38 candidate countries qualify; in 18 of them real hourly earnings in manufacturing were higher in 2025 than in 2019 (median change +2.2%). The lowest were Sweden (-5.4%), Czechia (-3.4%), Italy (-2.9%), Finland (-2.7%) and Germany (-2.6%, four of six years falling); the highest Mexico (+31.5%), Hungary (+19.8%) and Israel (+15.0%). With base 2015 the median is +7.4% and 20 of 25 are higher. **Dropped, and why:** the United States (no complete 2025 CPI average, because October 2025 is missing); Belgium (wage index ends 2025-04); Austria (ends 2024-12); Portugal (2024-01), Luxembourg (2024-10) and Türkiye (2023-10), whose indices stop in or before 2024; and Switzerland, Greece, Latvia, Lithuania, Chile, Colombia and Costa Rica, for which I found no OECD hourly-earnings series on FRED. If the last year is 2024, 28 countries qualify, including the United States (+2.3% since 2019).

## Limits
* **Wages against CPI is not a living-standards measure.** Average hourly earnings change with the mix of jobs (the April 2020 jump) and with who is employed. They exclude benefits such as health insurance and pensions, taxes and transfers, and they say nothing about hours or about household income and unemployment. `AHETPI` covers production and nonsupervisory employees only, which is why the three wage series disagree about the post-2019 gain.
* **CPI-U is one particular price index.** It has its own measurement issues (substitution between goods, quality adjustment, the treatment of housing), and households with different spending patterns face different inflation. A real wage deflated by CPI-U is not a measure of anyone's actual purchasing power.
* **The lead/lag result is descriptive.** Cross-correlation of persistent series gives broad, unstable peaks; it is not a test of a wage-price spiral and does not show which variable causes the other. It uses the longest unbroken stretch of data, not the whole sample, around the missing October 2025 CPI.
* **Episode counts depend on choices.** The six-month minimum and the strict "inflation above wage growth" rule count marginal runs (calendar years 1994 and 1995 show a gap of 0.0 pp) alongside severe ones; the mean and peak gaps are the better guide to severity.
* **The panel is narrow.** It covers hourly earnings in manufacturing only, annual averages, and the OECD's earnings concepts differ somewhat across countries. Prices are World Bank annual CPI inflation (the US uses `CPIAUCSL` annual averages), not the OECD series that would match the wage data, because those series are stale. The latest-year values may be provisional, and the dropped-country list reflects what I could find on FRED, not what exists.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/015-inflation-vs-wages/app.py
    pytest projects/015-inflation-vs-wages
