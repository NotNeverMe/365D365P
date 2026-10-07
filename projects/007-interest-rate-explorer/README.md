# 007 · Interest-Rate Explorer

> How do central-bank policy rates compare with inflation and growth, and how often have real rates been negative?

## What it does
Pick one of 14 economies and see its policy rate next to year-on-year inflation and real GDP growth, then the real policy rate (nominal minus inflation) with every negative spell shaded and counted. Two US-only tabs compare the federal funds rate with a Taylor-rule benchmark (adjustable r*, inflation target and inflation measure) and list every US hiking cycle with its trough, lift-off, peak and the cut that followed.

## Data

| What | Source and id | Coverage used |
|---|---|---|
| US policy rate | FRED `FEDFUNDS` (monthly average) | 1954-07 to 2026-09 |
| US inflation | FRED `CPIAUCSL` (headline), `CPILFESL` (core), year-on-year | to 2026-08; no October 2025 observation in the series |
| US output gap | FRED `GDPC1` real GDP against CBO potential `GDPPOT` | 1947 Q1 to 2026 Q2 (potential cut at the last GDP quarter; FRED carries CBO projections to 2036) |
| Policy rates, 13 other economies | BIS `WS_CBPOL`, monthly end of period | e.g. euro area 1999-01, UK 1946-01, Korea 1999-05, all to 2026-06 or later |
| Inflation, 13 other economies | BIS `WS_LONG_CPI`, year-on-year %, monthly | all to 2026-06 or later |
| Euro area deposit facility rate (option) | FRED `ECBDFR`, daily, averaged to months | 1999-01 to 2026-10 |
| Growth, 13 other economies | World Bank `NY.GDP.MKTP.KD.ZG`, annual (euro area = `EMU`) | 1961 to 2025 |

Economies: United States, euro area, United Kingdom, Japan, Canada, Switzerland, Australia, Sweden, South Korea, India, Brazil, Mexico, South Africa, Turkey. The BIS series are downloaded once through `stats.bis.org` and cached in `data/bis/` (124 KB); FRED and World Bank data come from `core.fred` and `core.worldbank`.

**Series checked and not used.** The OECD short-term-rate series on FRED are stale or gone: `IRSTCB01JPM156N`, `IRSTCB01CAM156N`, `IRSTCB01INM156N`, `IRSTCB01BRM156N` and `IRSTCB01ZAM156N` all end in 2023-12; `IRSTCB01GBM156N`, `IRSTCB01AUM156N`, `IRSTCB01CHM156N`, `IRSTCB01KRM156N`, `IRSTCB01MXM156N` and `IRSTCB01EZM156N` return HTTP 404. The OECD CPI growth series also stop early (`CPALTT01JPM659N` in 2021-06, the euro-area series in 2023-01). The BIS replaces all of them with current data. `ECBDFR` loads and is current.

## Method
* **Inflation**: percentage change against the same month a year earlier, computed on a complete calendar so a missing month leaves a gap instead of mis-aligning the comparison (`CPIAUCSL` really does skip 2025-10).
* **Real policy rate** = policy rate − year-on-year CPI inflation, in the same month. This is the ex-post, backward-looking measure.
* **Negative spells**: runs of consecutive months with a negative real rate; a missing month ends a run.
* **Hiking cycles**: a zig-zag filter on the funds rate. A peak (trough) is confirmed once the rate has reversed by at least 1.5 percentage points (adjustable). Each trough-to-peak rise is a cycle. *Lift-off* is the first month the rate is at least 0.25 pp above the trough, which matters when the rate sits on a floor for years.
* **Taylor rule** (Taylor 1993 weights): `i = r* + π + 0.5 (π − π*) + 0.5 · gap`, with r* = 2, π* = 2, π = year-on-year CPI averaged over the quarter, and `gap = 100 (GDPC1 − GDPPOT) / GDPPOT`. The funds rate is averaged over the quarter. Only quarters with all three months of data are used.

## What the data say
Reproduce every number with `python projects/007-interest-rate-explorer/interest_rates.py`.

1. **US real rates were negative about a third of the time.** 284 of 865 months (32.8%) from 1954-07 to 2026-08. The longest spell ran 62 months (2009-11 to 2014-12, average −1.88 pp); the deepest was in 2022-03 at −8.37 pp, within a 42-month spell from 2019-11 to 2023-04 that averaged −3.49 pp. In 2026-08 the real rate was +0.28 pp (funds rate 3.63, inflation 3.35).
2. **The 2021-23 dip was nearly universal.** For 13 of the 14 economies the lowest real policy rate since 2000 falls between 2021-07 (Brazil) and 2023-01 (Japan): United States −8.37 pp (2022-03), euro area −9.36 (2022-10), United Kingdom −8.84 (2022-10), Sweden −9.83 (2022-12), Turkey −75.4 (2022-11). India is the exception (−5.75 in 2010-04).
3. **Definitions matter for the euro area.** Negative real-rate months since 1999-01: 184 of 332 using the BIS series (main refinancing rate, deposit rate from 2024-09) but 240 of 332 using the deposit facility rate `ECBDFR`, which the ECB sets below the main refinancing rate.
4. **US policy tracked the Taylor rule closely in 1987-2001, then fell well below it.** The 1987-2001 average gap was only −0.34 pp. In 2002-2005 all 16 quarters were below the rule: funds rate 1.84% on average against 4.43% prescribed, a gap of −2.59 pp. In 2021-2022 the average gap was −10.06 pp and the widest was −13.53 pp in 2022 Q1. With core CPI instead of headline the figures are −1.76 pp and −7.83 pp (widest −10.99 pp). In the latest quarter (2026 Q2) the funds rate was 3.63% against a rule of 7.40% (headline; 5.77% with core), a gap of −3.77 pp (−2.13 pp). The zero lower bound explains little of the 2009-2015 gap of −1.62 pp: the rule itself (headline CPI) was negative in only 3 of those 28 quarters.
5. **The 2022-23 hiking cycle was the largest US rise since 1980-81** The funds rate went from 0.05% (trough 2020-04; first real increase 2022-04) to 5.33% in 2023-08, a rise of 5.28 pp in 16 months from lift-off. The next largest since 1981 was +4.28 pp (2003-12 to 2007-02, 31 months from lift-off 2004-07). The filter finds 17 trough-to-peak rises since 1954-07; the cut after the latest peak (to 3.63% by 2026-05, 1.70 pp) was still unconfirmed at the end of the data.

## Limits
* Real rates here are **ex post**: they subtract inflation that has already happened, not the inflation people expected when the rate was set.
* BIS rates are end-of-month; US and ECB rates are monthly averages. Differences of a few basis points to a quarter point appear in months with a move.
* **Hyperinflation** wrecks the real-rate scale (Brazil 1990, Japan 1947, Turkey 2022). The app crops axes to the central 98% of values by default and says how many months fall outside; the data and tables are never cropped.
* The Taylor rule is mechanical and sensitive to its inputs: headline vs core CPI moves the 2021-22 gap by about 2 pp, and r* and π* are choices. The potential-GDP estimate is today's CBO series, not what policymakers could see at the time. A gap to the rule is a description, not proof that policy was mistaken.
* The 2025 Q4 Taylor quarter is missing because October 2025 CPI is absent from `CPIAUCSL`.
* The latest month differs by economy: India's policy rate and Australia's inflation end in 2026-06, a few others in 2026-07, most in 2026-08. The module's coverage table lists each.
* Growth for non-US economies is annual, so it can only be compared with monthly rates at that resolution.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/007-interest-rate-explorer/app.py
    pytest projects/007-interest-rate-explorer
