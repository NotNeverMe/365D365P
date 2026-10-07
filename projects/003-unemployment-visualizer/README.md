# 003 · Unemployment visualizer

> How does unemployment differ by country, gender, age and education, and where are the gaps largest?

## What it does
Choose countries and a window of years to see unemployment trends for the total, female, male and youth rates. Separate tabs show the gender gap and the youth-to-all-ages multiple against the all-economy median, an education comparison (basic, intermediate, advanced) for a country and year, and rankings of the countries with the largest gaps. Because the education series are sparse, the app says which year it actually used and how many economies stand behind each comparison.

## Data
All from the World Bank World Development Indicators, through `core.worldbank` (cached under `data/worldbank/`, licence CC BY 4.0). 217 economies are on the World Bank list.

| Indicator | Series | Origin | Economies | Observations | Years | Median years per economy |
|---|---|---|---|---|---|---|
| `SL.UEM.TOTL.ZS` | Total, % of labour force | ILO modelled estimate | 187 | 6,531 | 1991-2025 | 35 |
| `SL.UEM.TOTL.FE.ZS` | Female | ILO modelled estimate | 187 | 6,531 | 1991-2025 | 35 |
| `SL.UEM.TOTL.MA.ZS` | Male | ILO modelled estimate | 187 | 6,531 | 1991-2025 | 35 |
| `SL.UEM.1524.ZS` | Youth, ages 15-24 | ILO modelled estimate | 187 | 6,531 | 1991-2025 | 35 |
| `SL.UEM.BASC.ZS` | Basic education | ILO Education and Mismatch Indicators | 187 | 2,475 | 1970-2025 | 9 |
| `SL.UEM.INTM.ZS` | Intermediate education | ILO Education and Mismatch Indicators | 189 | 2,466 | 1970-2025 | 9 |
| `SL.UEM.ADVN.ZS` | Advanced education | ILO Education and Mismatch Indicators | 188 | 2,422 | 1970-2025 | 9 |

The education series are not modelled estimates: the World Bank sources them from the ILO's survey-based Education and Mismatch Indicators, so a country-year exists only where a labour force survey does. How many economies report in a given year (basic / intermediate / advanced education):

| Year | 2000 | 2010 | 2019 | 2024 | 2025 |
|---|---|---|---|---|---|
| Economies | 50 / 50 / 47 | 103 / 102 / 98 | 121 / 123 / 119 | 94 / 92 / 94 | 17 / 17 / 17 |
| With all three | 47 | 95 | 117 | 92 | 17 |

The first four series cover 182 to 187 economies in every year from 1991 to 2025.

## Method
* **Gender gap** = female rate minus male rate, in percentage points. Positive means women are worse off.
* **Youth ratio** = youth (15-24) rate divided by the all-ages (15+) rate. The all-ages rate includes young workers, so this understates the true youth-to-adult (25+) ratio. The World Bank does not publish an adult-only rate, so this is the closest honest version.
* **Education gap** = basic minus advanced education rate, in percentage points. Positive means the less educated are worse off; negative means graduates are.
* **Handling the sparse education data.** The education chart uses the selected year if the country reports it, otherwise the latest earlier year within five years, and says so. Rankings use each economy's latest complete (all three levels) record within five years of the selected year and show the year used. Nothing is interpolated.
* **"All-economy median"** lines are a plain median across economies, not weighted by labour force.

## What the data say
All numbers come from `python projects/003-unemployment-visualizer/unemployment.py`. The comparison year is 2024, the latest year in which the education series still cover at least 75% of their best year.

1. **Women have the higher rate in most economies, but the median gap is small.** In 2024, 125 of 182 economies had higher female unemployment, with a median gap of +0.61 pp. The median gap was 0.63 pp in 1991, 1.02 pp in 2000, 0.88 pp in 2019 and 0.61 pp in 2024.
2. **A few countries drive the extremes.** The largest female-higher gaps in 2024 are Iraq (29.7% vs 13.1%, a gap of 16.6 pp), Syria (14.5 pp), Gabon (14.2 pp), Djibouti (13.8 pp) and Yemen (13.4 pp). The largest male-higher gap is only -4.2 pp (Tajikistan), then St Vincent and the Grenadines (-3.3) and Turkmenistan (-3.1).
3. **Youth unemployment is typically more than double the all-ages rate.** The 2024 median youth rate is 12.9% against 5.1% overall, a median ratio of 2.32. Only 3 of 182 economies have a youth rate below the all-ages rate. The ratio is highest in countries with very low overall unemployment: Kuwait 7.0 (15.1% vs 2.2%), Thailand 6.0 (4.7% vs 0.8%), Bhutan 5.5.
4. **More education does not always mean less unemployment.** In 2024 itself, 33 of the 92 economies with a complete education record have a higher advanced-education rate than basic-education rate; using the five-year fallback it is 70 of 155. The US shows the textbook pattern (basic 6.5%, advanced 2.6%), India the reverse (basic 2.3%, advanced 13.5%). The biggest basic-over-advanced gaps are the Slovak Republic (40.1% vs 2.0%) and South Africa (39.3% vs 12.8%).
5. **The 2020 shock is visible in the median:** total unemployment was 5.36% in 2019, 6.38% in 2020 and 5.14% in 2024.

## Limits
* **Education data are thin.** Each education series has a median of 9 years per economy against 35 for the headline series, and about half the economies report in a given year (92 report all three in 2024, 17 in 2025). The "70 of 155" figure mixes years (2019-2024); the "33 of 92" figure does not, but covers fewer, and not randomly chosen, economies.
* **Modelled, not measured.** Headline, gender and youth rates are ILO modelled estimates. The ILO imputes years without a labour force survey, and the latest years are estimates that may be revised, so small year-to-year moves in a single country should not be over-read.
* **No true youth-to-adult ratio.** See Method. The ratio shown understates it.
* **Comparability.** Definitions follow ILO standards, but informal-economy size, survey coverage and the meaning of "basic", "intermediate" and "advanced" education (grouped from national school systems) differ between countries. Unemployment is a share of the labour force, so a low rate can reflect discouraged workers leaving the labour force rather than good jobs.
* **Unweighted.** Medians treat a small economy and India alike.
* **Economies only.** World Bank aggregates (regions, income groups) are excluded.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/003-unemployment-visualizer/app.py
    pytest projects/003-unemployment-visualizer
