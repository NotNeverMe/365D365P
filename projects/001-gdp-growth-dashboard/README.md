# 001 · GDP growth dashboard

> Which economies grew fastest over a chosen window, how bumpy was the ride, and when did output actually fall?

## What it does
Pick any World Bank economies and a window of years. The app plots annual growth (with recession years below the zero line), GDP rebased to 100 at the start of the window, and a growth-versus-volatility scatter of every economy for context. A summary table gives each country's compound growth, volatility, recession years and rank, with decade averages and a coverage table underneath. A switch moves everything from total GDP to GDP per capita.

## Data
| Source | Indicator | Used for | Coverage |
|---|---|---|---|
| World Bank WDI | `NY.GDP.MKTP.KD.ZG` GDP growth (annual %) | volatility, recessions, decade averages | 214 economies, 1961-2025 |
| World Bank WDI | `NY.GDP.MKTP.KD` GDP (constant 2015 US$) | CAGR, rebased index, size filter | 213 economies, 1960-2025 |
| World Bank WDI | `NY.GDP.PCAP.KD.ZG` and `NY.GDP.PCAP.KD` | same, per capita | growth 214 economies (1961-2025), level 213 (1960-2025) |

Aggregates such as "World" or "Euro area" are dropped, leaving real economies only. Licence: World Bank open data (CC BY 4.0). Data are cached under `data/worldbank/` and read through `core.worldbank`, so the app runs offline.

## Method
* **Window.** For a window `(start, end)` the level at the end of `start` is the base. Growth rates are used for `start+1 ... end`, so the CAGR, the average, the volatility and the recession count all describe the same `end - start` annual changes.
* **CAGR** = `(GDP_end / GDP_start)^(1 / (end - start)) - 1`, computed from the levels. It is blank if either level is missing; nothing is interpolated.
* **Why not average the growth rates?** Growth of +50% then -50% averages 0% but leaves output 25% lower (1.5 x 0.5 = 0.75). The average of annual rates is never below the CAGR, and the gap grows with volatility. The summary table shows both.
* **Volatility** = sample standard deviation (n-1) of annual growth over the window, in percentage points. Needs at least three years.
* **Recession year** = negative annual growth. Annual data cannot see a quarterly "technical" recession.
* **Decade average** = mean of the annual growth rates in the decade, blank with fewer than five years (so most 2020s figures are a six-year average, 2020-2025).
* **Ranking** = CAGR over all economies that have a level in both end years. An optional size filter drops economies whose base-year GDP is below a threshold in constant US$, because very small economies otherwise crowd the top.

## What the data say
All numbers come from `python projects/001-gdp-growth-dashboard/gdp_growth.py` (window 2000-2024; 2024 is the latest year reported by at least 90% of economies).

| Country | CAGR % | Average of annual % | Volatility (pp) | Recession years |
|---|---|---|---|---|
| China | 8.14 | 8.18 | 2.77 | none |
| India | 6.26 | 6.30 | 3.06 | 2020 |
| Brazil | 2.26 | 2.30 | 2.86 | 2009, 2015, 2016, 2020 |
| United States | 2.13 | 2.14 | 1.76 | 2009, 2020 |
| United Kingdom | 1.51 | 1.57 | 3.32 | 2008, 2009, 2020 |
| Germany | 1.01 | 1.04 | 2.33 | 2002, 2003, 2009, 2020, 2023, 2024 |
| Japan | 0.65 | 0.67 | 2.15 | 2008, 2009, 2011, 2019, 2020, 2024 |

1. **China is the only large economy that never contracted.** Its slowest year in 2001-2024 was 2020, at +2.34%. Germany and Japan each had six negative years, and Japan's compound growth of 0.65% a year is less than a third of the US rate (2.13%).
2. **Rankings depend on a size filter.** Among the 116 economies with base-year GDP of at least $10bn (2015 US$), China ranks 2nd (Ethiopia is 1st at 8.44%), India 9th, Brazil 82nd, the US 84th, the UK 94th, Germany 103rd and Japan 108th. With no filter, 193 economies qualify and the top three are Guyana, Ethiopia and China.
3. **Averaging growth rates overstates growth most for volatile economies.** Across 193 economies the average-minus-CAGR gap has a median of 0.058 pp but a 90th percentile of 0.257 pp. Libya's average growth is +2.70% a year while its CAGR is -0.06%, with a growth standard deviation of 24.9 pp.
4. **Recessions cluster.** In 2009, 105 of 209 economies reporting had negative growth (50%); in 2020, 170 of 210 (81%).
5. **Per head, the picture changes.** GDP per capita CAGR over 2000-2024 is 7.65% for China, 4.87% for India and 1.34% for the US; India's population growth takes about 1.4 points off its 6.26% GDP rate.
6. **Decade averages show the slowdowns** (mean of annual growth, %): China 10.4 in the 2000s, 7.7 in the 2010s, 4.9 in the 2020s; Japan 10.4 in the 1960s, 1.3 in the 2010s, 0.4 in the 2020s; Germany 0.1 in the 2020s.

## Limits
* **Constant 2015 US$ is not purchasing power.** Levels use a fixed base-year exchange rate. This is right for growth within a country but says little about living standards across countries.
* **Annual data only.** A technical recession (two negative quarters) can straddle a year with positive growth and will not be flagged.
* **Recent years are preliminary.** 186 of 214 economies report 2025; the slider opens on 2024 for that reason. Statistical offices revise GDP, sometimes heavily.
* **Gaps are not filled.** A country missing a year is summarised on the years it has (the table shows years with data versus expected), and its CAGR is blank if an end-year level is missing.
* **Small and resource-driven economies swing wildly** (Libya, Guyana, Macao), so extreme growth rates and volatility say more about their size than about policy.
* **Growth and levels are the same data.** The World Bank growth series is derived from the same constant-price levels (the tests check they agree to 1e-6 pp), so CAGR and annual growth cannot disagree, but neither validates the other.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/001-gdp-growth-dashboard/app.py
    pytest projects/001-gdp-growth-dashboard
