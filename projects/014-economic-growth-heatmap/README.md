# 014 · Economic Growth Heatmap

> Where in the world has the economy grown, and how fast, over any window since 1960, and how many countries were going backwards?

## What it does
A world map coloured by compound annual growth of GDP per capita or total GDP, for a decade preset or any two years you choose. A second, animated map steps through decades or 5-year windows on one fixed colour scale so that frames can be compared. Below the maps are the ten fastest and ten slowest economies, a median and interquartile-range summary by World Bank region, and the share of economies with negative growth in each window. Countries without data for a window are drawn grey and counted in a coverage figure.

## Data
| Source | Series | Coverage | Licence |
|---|---|---|---|
| World Bank WDI (`core.worldbank`) | `NY.GDP.PCAP.KD` GDP per capita, constant 2015 US$ | 1960-2025; 213 economies ever, 186 with a 2025 value | CC BY 4.0 |
| same | `NY.GDP.MKTP.KD` GDP, constant 2015 US$ | same years and economies | CC BY 4.0 |
| same | `NY.GDP.PCAP.KD.ZG` GDP per capita growth, annual % | 1961-2025; used only to compare the CAGR with the average of annual rates | CC BY 4.0 |
| World Bank country list (`core.worldbank.countries`) | region and income group | 217 economies (aggregates removed), 7 regions, 4 income groups | CC BY 4.0 |

Coverage grows over time. A window needs both end years, so the number of economies with a growth rate (of 217) is 107 for 1960-1970 (49%), 140 for 1970-1980, 159 for 1980-1990, 192 for 1990-2000, 199 for 2000-2010, 207 for 2010-2020 (95%) and 186 for 2020-2025 (86%).

## Method
* **Window growth is the compound annual growth rate (CAGR) of the level**: `(level_end / level_start)^(1 / (end - start)) - 1`, in percent. Only the two end years are used.
* **Why not the average of annual growth rates?** The arithmetic mean of annual rates overstates growth whenever growth is volatile, and it can have the wrong sign. If a level rises 50% and then falls 50%, the average rate is exactly 0% but the economy ends 25% smaller (CAGR -13.4% a year). By the AM-GM inequality the mean is never below the CAGR, and the CAGR is the one rate that carries the start level to the end level. The module reports both so the difference is visible.
* **Missing data stay visible.** Every economy is in every window table; if a start or end year is missing its growth is NaN and the map leaves it grey. Nothing is interpolated.
* **Windows.** Decades are 1960-1970, 1970-1980, ... 2010-2020, then 2020-2025, which is only five years. The 5-year windows are 1960-1965 through 2020-2025.
* **Fixed colour scale.** One symmetric diverging scale (red = shrinking, blue = growing) is used for the single map and every animation frame. Its default limit is the 90th percentile of |CAGR| across all decade windows, rounded up: 6% a year for GDP per capita, 7% for total GDP. A sidebar slider changes it. Values beyond the limit show the end colour; hover shows the exact number.
* **Region summary.** Median, first and third quartile and interquartile range (IQR) of window growth by World Bank region, using only economies with data.

## What the data say
Reproduce everything below with `python projects/014-economic-growth-heatmap/growth_heatmap.py`.

1. **Median GDP per capita growth by decade** (CAGR %, economies with data): 2.60 for 1960-70, 2.40 for 1970-80, **0.70 for 1980-90**, 1.48 for 1990-2000, 2.11 for 2000-10, **0.97 for 2010-20**, and 2.78 for 2020-25 (five years). The share of economies whose GDP per capita fell over the window peaked at **41% in the 1980s** (10%, 19%, 41%, 29%, 13%, 29% and 11% for the seven windows in order).
2. **1990-2019, GDP per capita:** 191 of 217 economies have data (88%); the median grew 1.57% a year and 11.0% shrank. The fastest ten were Equatorial Guinea (10.1%), China (8.7), Myanmar (7.6), Bosnia and Herzegovina (7.0), Honduras (5.9), Cabo Verde (5.7), Viet Nam (5.5), Bhutan (5.1), Lao PDR (4.9) and India (4.5). The slowest ten ran from Naoero (Nauru, -3.4%), Venezuela (-2.6) and the Democratic Republic of Congo (-1.9) to the Republic of Congo (-0.8). Several of these are very small or oil-dependent economies.
3. **Regions differ in level more than in spread.** For 1990-2019 South Asia's median is 4.15% a year (IQR 0.95, six economies) against 1.35% for Sub-Saharan Africa (IQR 1.94, 46 economies with data) and 1.14% for the Middle East, North Africa, Afghanistan and Pakistan (IQR 1.57). By income group the median ranges from 1.05% for low-income economies (IQR 2.87, first quartile -0.51%) to 1.90% for upper-middle-income ones.
4. **The mean of annual rates really does overstate.** For 1990-2019 across the 191 economies with every annual rate, the mean exceeds the CAGR for all of them (median gap 0.06 pp, 90th percentile 0.39 pp, maximum 2.87 pp). Equatorial Guinea's mean is 13.00% against a CAGR of 10.13%; Liberia's average annual growth is +1.48% although its GDP per capita fell 0.58% a year on a compound basis, ending below where it started.
5. **Population growth separates the two measures.** For 1990-2019 the median economy grew 3.12% a year in total GDP but 1.57% per head, and 17 economies shrank per head while total GDP grew.
6. **Recent windows.** The median GDP per capita growth was 1.74% in 2010-2019 (14.5% shrinking) and 1.34% in 2019-2025 (24.2% shrinking, 186 economies with data).

## Limits
* **Coverage is uneven.** Early windows cover about half of today's economies, usually those with better statistics, so comparing the 1960s with later decades compares different sets of countries. Grey countries are missing a start or end year, not necessarily missing growth.
* **Constant-price US$ levels, not PPP.** The World Bank revises these series and they use market exchange rates, so levels are not comparable across countries; growth rates are the comparable quantity. GDP also says nothing about distribution.
* **Window end points matter.** Compound growth depends on where in the business cycle the two years fall, and on commodity prices for oil exporters. The 2020-2025 window starts in 2020, the pandemic year, and has only five years.
* **Small economies dominate the extremes.** Island states and oil exporters top and bottom the lists; some are too small to see on the map. The map shows their colours only where the territory is large enough to render.
* **The colour limit clips outliers.** With a limit of 6% a year, a country growing 10% and one growing 7% look the same; the tables and hover text carry the exact values.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/014-economic-growth-heatmap/app.py
    pytest projects/014-economic-growth-heatmap
