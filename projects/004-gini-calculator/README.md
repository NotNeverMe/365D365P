# 004 · Gini Calculator

> How unequal is a set of incomes, how sure are we of that number, and how much does it lose when only quintile shares are published?

## What it does
Paste incomes or upload a CSV (with an optional weights column) and the app draws the Lorenz curve and reports the Gini coefficient with a bootstrap confidence interval, the quintile shares, the top 10% share and the Palma ratio. A second tab shows the latest World Bank survey Gini for every country, Lorenz curves rebuilt from World Bank quintile shares, and Gini trends over time. Examples include a lognormal distribution with a sigma slider and a Pareto distribution with an alpha slider, both with their theoretical Gini shown next to the estimate.

## Data
| Source | Indicator | Coverage | Licence |
|---|---|---|---|
| World Bank Poverty and Inequality Platform, via the World Bank Indicators API | `SI.POV.GINI` survey Gini, scale 0-100 | 171 countries, 1963-2025, irregular survey years | CC BY 4.0 |
| same | `SI.DST.FRST.20`, `SI.DST.02ND.20`, `SI.DST.03RD.20`, `SI.DST.04TH.20`, `SI.DST.05TH.20`: income share of each quintile, % | same country-years as the Gini (all six codes load and align) | CC BY 4.0 |

Your own data never leaves the session. Microdata calculations reuse `core/inequality.py` (`gini`, `lorenz_curve`, `group_shares`, `top_share`, `palma_ratio`).

## Method
* **Gini** is one minus twice the area under the Lorenz curve, computed by the trapezoid rule on the sorted, weighted observations. 0 means equal incomes, values near 1 mean one person holds almost everything.
* **Parsing** accepts numbers separated by spaces, commas, semicolons or new lines, or a CSV (delimiter detected, headerless files allowed). It rejects empty input, fewer than two observations, non-numbers, negatives, all-zero data and non-positive weights, and the message names the offending rows or columns.
* **Bootstrap interval**: resample observations (with their weights) with replacement, recompute the Gini each time, and take the 2.5th and 97.5th percentiles (for a 95% interval). The random generator is seeded, so a given dataset and seed always give the same interval.
* **Grouped-data Gini**: given the income shares of k equal-population groups, build Lorenz points (j/k, cumulative share of the poorest j groups) and apply the trapezoid rule. Joining the points with straight lines puts the curve above the true, convex Lorenz curve, so the estimate is a lower bound: it ignores inequality inside each group.
* **Lognormal benchmark**: for a lognormal distribution the Lorenz curve is L(p) = Φ(Φ⁻¹(p) − σ) and the Gini is erf(σ/2). Given a country's published Gini, that fixes σ and so the quintile-only Gini that a lognormal with that inequality would produce.

## What the data say
Reproduce everything below with `python projects/004-gini-calculator/gini_calc.py`.

1. **The quintile-only Gini understates the published Gini in every one of the 2,430 country-years**, by 2.90 Gini points on average (median 2.58, range 1.30 to 10.40). Using each country's latest survey (171 countries) the mean gap is 2.77 points, 7.6% of the published value, with a range of 1.54 to 5.54.
2. **The gap grows with inequality** (correlation between gap and published Gini 0.95 across latest surveys). Namibia 2015 has the largest gap: published 59.1, quintile-only 53.6, a difference of 5.5 points. The Slovak Republic 2023 has the smallest: 23.8 against 22.3, a gap of 1.5.
3. **Most of the gap is within-quintile inequality, not noise.** A lognormal distribution with each country's Gini would lose 2.47 points on average when reduced to quintiles, against 2.77 observed (correlation of predicted and observed gaps 0.95, mean absolute error 0.33). Real top tails are a little fatter than lognormal, so the observed gap is slightly larger.
4. **The same pattern in simulated data** (100,000 draws, seed 0): lognormal with σ = 0.8 has theoretical and sample Gini 0.428 but 0.398 from its quintile shares; lognormal σ = 1.2 gives 0.604 against 0.550; Pareto with α = 3 gives 0.200 against 0.184.
5. **The bootstrap interval is honest for moderate samples and too narrow for tiny ones.** In 150 simulated lognormal (σ = 0.8) samples, the 95% interval contained the true Gini 79% of the time at n = 50, 93% at n = 200 and 94% at n = 1,000 (200 resamples each).

## Limits
* The grouped estimator only recovers the Gini from the data the World Bank publishes as shares; it is not a substitute for microdata. Compared with the published Gini it is always lower, by an amount that depends on the shape of the distribution.
* World Bank Ginis are survey-based and mix income and consumption measures across countries, so cross-country comparisons are rough. Survey years differ (the median latest survey is 2021), and a country's line in the trend chart joins surveys that can be several years apart.
* Survey data miss the very top of the distribution, so published Ginis tend to sit below what tax-record-based measures would give.
* The percentile bootstrap assumes your observations are an independent random sample. It does not account for survey design effects, and the sample Gini is slightly biased downward in small samples, which is why coverage falls short at n = 50.
* Pasted numbers use commas as separators, so write 12000, not 12,000. Weighted data from a CSV need a weights column named `weight`/`weights` or named explicitly in the app.
* Extremely heavy-tailed data have an unstable Gini: for Pareto draws with α = 1.2 (theoretical Gini 0.714) the sample Gini of 2,000 draws ranged from 0.558 to 0.713 across 20 seeds, against 0.182 to 0.210 for α = 3.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/004-gini-calculator/app.py
    pytest projects/004-gini-calculator
