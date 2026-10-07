# 002 · Inflation tracker

> Which parts of the US consumer basket are driving inflation, and how does US inflation compare with the rest of the world?

## What it does
The first tab tracks US year-on-year CPI inflation and splits it into the percentage points contributed by each category: a stacked chart over time, plus a ranked breakdown for any month you choose. Three breakdowns are available (eight major groups; housing split so shelter stands alone; food / energy / core goods / core services). The second tab compares headline CPI inflation across countries using World Bank data.

**The category weights are estimated from the data, not official BLS weights** (see Method and Limits). Every chart and table that uses them says so.

## Data
All US series are FRED copies of BLS CPI-U (urban consumers, US city average), **not seasonally adjusted**, so the 12-month change equals the headline rate the BLS reports. All 16 ids load; all end in August 2026 (`python .../inflation_tracker.py` prints this catalogue).

| FRED id | Series | First month |
|---|---|---|
| `CPIAUCNS` | All items (headline) | 1913-01 |
| `CPIFABNS` | Food and beverages | 1967-01 |
| `CPIHOSNS` | Housing | 1967-01 |
| `CPIAPPNS` | Apparel | 1914-12 |
| `CPITRNNS` | Transportation | 1935-03 |
| `CPIMEDNS` | Medical care | 1935-03 |
| `CPIRECNS` | Recreation | 1993-01 |
| `CPIEDUNS` | Education and communication | 1993-01 |
| `CPIOGSNS` | Other goods and services | 1967-01 |
| `CUUR0000SAH1` | Shelter (part of housing) | 1952-12 |
| `CUUR0000SAH2` | Fuels and utilities (part of housing) | 1952-12 |
| `CUUR0000SAH3` | Household furnishings and operations (part of housing) | 1967-01 |
| `CPIUFDNS` | Food | 1913-01 |
| `CPIENGNS` | Energy | 1957-01 |
| `CUUR0000SACL1E` | Commodities less food and energy commodities ("core goods") | 1957-01 |
| `CUUR0000SASLE` | Services less energy services ("core services") | 1957-01 |

Every series is missing **October 2025**: FRED has no observation for that month (the BLS did not publish it). The analysis starts in January 1993, when the two newest series (recreation, education and communication) begin, so all three breakdowns cover the same period. Two ids suggested for this project do not exist on FRED and return HTTP 404: `CUSR0000SAT` (transportation; the working id is `CPITRNNS`) and `CUSR0000SAH` (housing; `CPIHOSNS`).

| Source | Series | Coverage |
|---|---|---|
| World Bank WDI (IMF International Financial Statistics) | `FP.CPI.TOTL.ZG` Inflation, consumer prices (annual %) | 193 economies, 1960-2025; 165 report 2025 |

Licences: FRED/BLS data are public domain US government statistics; World Bank open data is CC BY 4.0. Data are cached under `data/` and read through `core.fred` and `core.worldbank`.

## Method
**Official weights were not available.** The BLS relative-importance table is the right input, but `bls.gov` (the 2025 table in `.htm` and `.xlsx`, and `download.bls.gov/pub/time.series/cp/cp.item`) answered HTTP 403 "Access Denied" from this environment. That was treated as a policy block and not worked around.

**Estimated weights.** For each month `m`, regress the monthly log change of the all-items index on the monthly log changes of the categories, over the latest 60 usable months up to `m`, with a non-negative least-squares fit (`scipy.optimize.nnls`, no intercept). The coefficients are the estimated weights `w_i(m)`. A weight is only reported once 48 monthly changes are available, so contributions start in January 1998.

**Contribution.** `contribution_i(t) = w_i(t - 12 months) x yoy_i(t)`, in percentage points: the weight at the base month of the comparison times the category's own 12-month change. `Residual` is the headline rate minus the sum of contributions, so the stacked bars always add exactly to the headline line. The residual absorbs estimation error and the drift of true weights over the year.

**Partitions, not overlapping categories.** Energy sits inside both housing (utilities) and transportation (motor fuel), so stacking food, shelter, energy, transportation and the rest would double count. Each breakdown instead splits the whole index into non-overlapping pieces.

**Gaps.** 12-month changes are computed on a gap-free monthly calendar, so a missing month is a hole rather than silently shifting every later comparison. (`core.stats.yoy_change` counts positions, so it would be wrong on these series after October 2025.)

## What the data say
All numbers come from `python projects/002-inflation-tracker/inflation_tracker.py`.

1. **Latest month: August 2026, headline 3.40%** (index 334.980 against 323.976 a year earlier). With the eight major groups, housing contributes 1.38 pp (41% of the headline) and transportation 1.08 pp (32%); food and beverages add 0.37 pp. Splitting housing out, shelter contributes 1.01 pp (30%) and transportation is then the largest single group.
2. **Energy is the swing factor.** In the four-way breakdown, energy contributes 1.27 pp (37% of the headline) from an estimated weight of just 7.8%, because its own 12-month change is 16.3%. Core services contribute 1.78 pp (52%), core goods 0.13 pp, food 0.35 pp.
3. **The 2022 peak was June 2022, at 9.06%.** Transportation contributed 3.15 pp (35%), housing 3.02 pp (33%, of which shelter 1.87 pp), food and beverages 1.75 pp (19%). In the four-way split, energy contributed 2.92 pp, core services 3.18 pp, food 1.68 pp and core goods 1.40 pp.
4. **The estimated weights reproduce the headline well.** Across the 343 months with contributions (January 1998 to August 2026, no October 2025), the residual averages 0.073 pp for the eight groups (largest 0.35 pp), 0.074 pp when housing is split (0.37 pp) and 0.101 pp for the four-way split (0.71 pp). The unconstrained weights sum to between 0.966 and 1.028 (eight groups) without being told to sum to one, which is a useful check that the fit finds a real partition. The estimated shelter weight for the August 2025 base month is 33.2%.
5. **Other countries, 2022.** US inflation was 8.0%, the UK 7.9%, Germany 6.9%, Japan 2.5%; Argentina 72.4% and Lebanon 171% (the highest of any economy). 63 of 178 economies reporting had inflation above 10% in 2022, falling to 22 of 174 in 2024.
6. **The two sources agree.** The US calendar-year average inflation computed from FRED matches the World Bank US figure for every year from 1994 to 2024 to within 0.0001 pp.

## Limits
* **Weights are estimates.** The official table could not be downloaded, so category weights come from a regression and carry error. Each uses the previous five years, so it lags real changes in spending patterns. In 5.6% of months (eight groups) a weight is pinned at zero, most often education and communication (5.3% of months), a small group whose price moves are hard to tell apart from the rest.
* **Residual.** Contributions do not add exactly to the headline unless `Residual` is included. It is shown in the chart, the table and the download.
* **Category definitions overlap in the real world.** "Transportation" mixes cars, insurance and motor fuel; the four-way split separates energy, but then core services lumps shelter, medical care and more together.
* **US CPI-U only, not seasonally adjusted.** Not CPI-W, not PCE (the Fed's preferred measure), not regional.
* **October 2025 is missing**, so there is no 12-month change for October 2025 or October 2026, and no contribution for those months.
* **Cross-country comparison is rough.** National CPI baskets, weights and methods differ, and the World Bank series is an annual average rather than December on December (checked for the US only). Hyperinflations (Lebanon, Argentina, Zimbabwe) dwarf everything else, so the chart opens zoomed to -5% to 30%.
* **Coverage varies by year.** 165 economies report 2025 against 193 that ever report; recent years may be revised.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/002-inflation-tracker/app.py
    pytest projects/002-inflation-tracker
