# 013 · Productivity Analyzer

> Which countries produce the most per worker and per hour, how large is the gap between agriculture, industry and services, and how much of productivity growth comes from workers moving between sectors rather than from each sector improving?

## What it does
Pick countries and a window of years. The app plots output per worker (or an estimate of output per hour) relative to the United States (US = 100), the compound growth rate over the window, value added per worker in agriculture, industry and services, and a shift-share decomposition of aggregate productivity growth into within-sector improvement, between-sector structural change and an interaction term. One table and a CSV download collect every number shown.

## Data
| Source | Series | Coverage | Licence |
|---|---|---|---|
| World Bank WDI (`core.worldbank`) | `SL.GDP.PCAP.EM.KD` GDP per person employed, constant 2021 PPP $ | 1991-2025; 177 economies ever, 168 in 2025 (of 217) | CC BY 4.0 |
| same | `NV.AGR.EMPL.KD`, `NV.IND.EMPL.KD`, `NV.SRV.EMPL.KD` value added per worker, constant 2015 US$ | 1991-2025; 179 / 180 / 180 economies ever, 151 / 150 / 150 in 2025. **The US has 2015 only.** | CC BY 4.0 |
| same | `SL.AGR.EMPL.ZS`, `SL.IND.EMPL.ZS`, `SL.SRV.EMPL.ZS` employment share, % (modelled ILO estimates) | 1991-2025; 187 economies ever, 182 in 2025 | CC BY 4.0 |
| Penn World Table, via FRED (`core.fred`) | `AVHWPE<ISO2>A065NRUG` average annual hours per person engaged | 60 countries, 1950-2023 (China is not on FRED) | PWT is CC BY 4.0; republished by FRED |
| FRED | `OPHNFB` US nonfarm business output per hour, index 2017 = 100 | 1947-2026Q2 (annual averages of complete years: 1947-2025) | public (BLS) |

All seven World Bank codes and the 60 hours series were loaded and checked before use. Sector value added per worker and the headline per-worker series are in different units (market-rate 2015 US$ versus 2021 PPP $); their logs correlate at 0.961 across 172 economies in 2019, but levels from the two are never mixed.

## Method
* **Relative to the US.** `100 * x(country, year) / x(US, same year)`.
* **Growth over a window.** Compound annual growth between the first and last year, `(x_end / x_start)^(1 / years) - 1`. Both end years must exist; nothing is filled in.
* **Output per hour (estimate).** GDP per person employed divided by Penn World Table annual hours per person engaged. World Bank/ILO employment and PWT hours come from different sources, so this is an estimate, not an official hours-based series.
* **Sector gap.** For each country and year: the ratios industry/agriculture and services/agriculture, best-over-worst sector, and the agricultural productivity gap `APG = (value added per worker outside agriculture) / (value added per worker in agriculture)`, where the non-agricultural figure is employment-weighted over industry and services.
* **Shift-share decomposition.** Aggregate productivity is `P = sum_i s_i * p_i`, with `s_i` the employment share of sector i (rescaled to sum to 1) and `p_i` its value added per worker. Between date 0 and date 1, with `dp = p1 - p0` and `ds = s1 - s0`:

      P1 - P0  =  sum s0*dp   +   sum p0*ds   +   sum ds*dp
                  within          between         interaction

  *Within* is the change if every sector improved but employment shares had stayed at their date-0 values. *Between* is the change if shares moved but each sector's productivity had stayed at date 0, so moving workers out of low-productivity sectors counts here. *Interaction* is workers moving into sectors whose own productivity also changed. The three terms add up to the total exactly (it is an identity). They are reported as percentage points of growth, `term / P0 * 100`. This is the Fabricant (1942) shift-share approach as used by McMillan and Rodrik (2011); other conventions assign the interaction to the between term, which changes the split but not the total. The unit test uses a two-sector example worked by hand: shares (0.6, 0.4) to (0.4, 0.6), productivity (10, 30) to (15, 36), so P goes from 18 to 27.6 and within 5.4 + between 4.0 + interaction 0.2 = 9.6.

## What the data say
Reproduce everything below with `python projects/013-productivity-analyzer/productivity.py`.

1. **Hours change the ranking.** In 2023 Germany produced 82.2% of US GDP per person employed but, on the per-hour estimate, 110.1% of the US figure: its workers log 1,335 hours a year against 1,789 in the US. Of 59 countries with hours data, 5 beat the US per worker and 12 beat it per hour; the seven that do so per hour but not per worker are Austria, Belgium, Germany, Denmark, France, the Netherlands and Sweden.
2. **Poorer countries grew faster, but not reliably.** Across 175 economies, GDP per worker grew at a median 1.62% a year in 2000-2019 against 1.29% for the US; the correlation between the log of the initial level relative to the US and subsequent growth is -0.47 (n = 174). The fastest were Myanmar (8.7%) and China (8.6%); the slowest were oil exporters such as Oman (-2.7%) and the United Arab Emirates (-2.0%).
3. **Agriculture is almost always the least productive sector, and the gap is widest where it employs most.** In 2019 agriculture had the lowest value added per worker in 88% of 173 economies. The median services/agriculture ratio is 2.3 and industry/agriculture 2.6. The median APG is 3.47 in low-income countries, where the median agricultural employment share is 60%, against 1.71 in high-income countries (3%).
4. **Structural change mattered most where workers left farms.** In 2000-2019, across 149 economies with complete sector data, the between-sector term was positive in 83%; the median contributions to growth were 30.5 pp within, 4.5 pp between, -0.7 pp interaction. Viet Nam is the extreme: 62.6 of its 105.5 pp of growth (59%) came from the between term. China grew 368.2% (257.8 pp within, 35.1 between, 75.3 interaction); India 142.5% (99.1 within, 23.6 between, 19.9 interaction). The median between-sector contribution is 14.2 pp in Sub-Saharan Africa and 19.3 pp in South Asia against 1.9 pp in high-income countries. The decomposition identity holds to 1e-13 pp for all 149.
5. **Three US measures, three growth rates.** For 1991-2023 US GDP per person employed grew 1.55% a year, GDP per hour (the World Bank/PWT estimate) 1.62%, and nonfarm business output per hour (`OPHNFB`) 2.02%. US hours per engaged person fell from 1,828 to 1,789. The business-sector series has a narrower scope and different output measurement, so the gap is not a pure hours effect.

## Limits
* **Three broad sectors only.** The brief asks about industries; the World Bank gives agriculture, industry (including construction) and services. Finer industry detail (manufacturing, ICT, finance) would need the GGDC 10-Sector Database, OECD STAN or EU KLEMS. I did not add them because I could not verify a machine-readable file that is reachable from the build environment.
* **Output per hour is derived and partial.** It covers 60 countries up to 2023, excludes China, and joins employed persons (ILO via the World Bank) with persons engaged (PWT). It will not match OECD hours-based productivity exactly.
* **The US has no sector series after 2015.** The World Bank publishes US sector value added per worker for 2015 only, so the US appears in the headline levels, the per-hour estimate and the `OPHNFB` cross-check but cannot appear in the sector-gap or shift-share charts. It is the benchmark only for the aggregate series.
* **Units differ across series.** Sector series are in market-exchange-rate US$, which understates real productivity in poorer countries relative to PPP. Ratios between sectors within a country are unit-free; levels are not comparable with the PPP headline.
* **Employment shares are modelled.** The ILO estimates smooth and extrapolate shares, so measured between-sector change partly reflects the model. Informal and self-employed workers are counted equally with others, and hours are not adjusted in the sector series.
* **Shift-share is accounting, not causation.** The within/between split depends on how sectors are aggregated (three sectors hide moves such as informal to formal services) and on the weights chosen. Window end points matter: 2000-2019 avoids the pandemic but still starts and ends at different points of commodity and business cycles.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/013-productivity-analyzer/app.py
    pytest projects/013-productivity-analyzer
