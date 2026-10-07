# 365 Projects

365 projects at the intersection of **economics, politics, philosophy and computer science**, built in public.
The rule for every project: real data or real users, a question stated up front, a check that the result is
right, and an honest page on what it cannot tell you.

Gallery and live site: **https://varad-patel.github.io/365projects/** (code: [varad-patel.github.io](https://github.com/varad-patel/varad-patel.github.io)).

This repo is a monorepo. Shared code (data loaders with caching, statistics, charts, UI helpers) lives in
[`core/`](core), and each project lives in its own folder under [`projects/`](projects) with its own README,
analysis module, Streamlit app and tests.

## Progress

**Economics × Data Science dashboards (1–15): done.** Each one answers a specific question, runs offline on the
committed data, and has unit tests plus an app smoke test.

| # | Project | What it answers | One finding from the data |
|--:|---|---|---|
| 1 | [GDP Growth Dashboard](projects/001-gdp-growth-dashboard) | How fast has each economy grown, and how volatile was it? | China's real GDP grew 8.14% a year over 2000–2024 with no recession year, 2nd of 116 economies above $10bn. |
| 2 | [Inflation Tracker](projects/002-inflation-tracker) | Which CPI categories drive US inflation? | Housing added 1.38 pp and transportation 1.08 pp to the 3.40% rate in Aug 2026. |
| 3 | [Unemployment Visualizer](projects/003-unemployment-visualizer) | Who is unemployed, by country, age, gender and education? | Female unemployment was higher in 125 of 182 economies in 2024. |
| 4 | [Gini Calculator](projects/004-gini-calculator) | How unequal is a distribution, and how much does grouped data hide? | Quintile-only Ginis understate the published figure in all 2,430 country-years, by 2.90 points on average. |
| 5 | [Cost-of-Living Index](projects/005-cost-of-living-index) | What salary elsewhere matches mine? | US$100,000 in New York matches US$91,584 in Dallas (BEA regional price parities, 2024). |
| 6 | [Purchasing Power Explorer](projects/006-purchasing-power-explorer) | What does a currency actually buy? | Richer countries are pricier: a 0.196 slope of log price level on log income in 2024 (n=174). |
| 7 | [Interest Rate Explorer](projects/007-interest-rate-explorer) | How do policy rates track inflation and growth? | The US real policy rate was negative in 284 of 865 months, deepest at −8.37 pp in March 2022. |
| 8 | [Currency Volatility Analyzer](projects/008-currency-volatility-analyzer) | When are exchange rates unstable? | Since 1999 the Brazilian real (16.5%) and South African rand (16.2%) are the most volatile of 12; the yuan is the least (2.8%). |
| 9 | [Trade Balance Visualizer](projects/009-trade-balance-visualizer) | Who runs trade surpluses and deficits, with whom? | The US has run a goods-and-services deficit every year since 1976; 2024 was −US$898.5bn. |
| 10 | [Government Spending Explorer](projects/010-government-spending-explorer) | Where does government money go? | Interest took 41.3% of Sri Lanka's central-government expense in 2022; the median country spent 5.2%. |
| 11 | [National Debt Dashboard](projects/011-national-debt-dashboard) | Who is most indebted against revenue, not just GDP? | The two rankings correlate at only 0.76 in 2022: Somalia is 32nd on debt-to-GDP but 1st at 16.8 years of revenue. |
| 12 | [GDP-per-Capita Explorer](projects/012-gdp-per-capita-explorer) | Are poor countries catching up? | Beta-convergence over 1990–2024 is −0.395 (se 0.108, n=183), and the weighted cross-country Gini fell from 0.609 to 0.455. |
| 13 | [Productivity Analyzer](projects/013-productivity-analyzer) | Who produces most per worker and per hour? | Germany is at 82.2% of US output per worker in 2023 but 110.1% per hour. |
| 14 | [Economic Growth Heatmap](projects/014-economic-growth-heatmap) | Where and when did growth happen? | The share of economies with falling GDP per capita peaked at 41% in the 1980s. |
| 15 | [Inflation vs Wages](projects/015-inflation-vs-wages) | Do wages keep pace with prices? | US real wages (production workers) are 6.3% above January 2019 but only 1.6% above January 2021. |

Every number above is reproduced by running the project's module, for example
`python projects/001-gdp-growth-dashboard/gdp_growth.py`. Data change as sources are revised, so a fresh
download can move them slightly.

**Next:** projects 16–49 continue the economics block, then [#50 PolicySim](docs/ROADMAP.md), the first
flagship, builds on the Gini, growth and tax code from this first batch.

## Run it

```bash
git clone <this repo> && cd 365-projects
pip install -e ".[dev]"           # Python 3.11+
streamlit run projects/001-gdp-growth-dashboard/app.py
pytest                            # 400+ tests, offline
```

`make run P=004` launches project 4, `make test` runs the suite and `make refresh-data` clears the cached
downloads so the next run fetches fresh data.

## How the data work

Loaders in `core/` download a dataset the first time it is needed and cache it under `data/`. The cache is
committed, so apps and tests run offline and results are reproducible.

| Source | Used for | Access |
|---|---|---|
| World Bank Indicators API | growth, prices, labour, trade, government finance, income | `core.worldbank` |
| FRED (St. Louis Fed) | US prices and wages, policy rates, exchange rates, hours | `core.fred` |
| The Economist Big Mac index | currency valuation | `core.bigmac` |
| BEA, BIS, Eurostat, WITS | regional prices, central-bank rates, spending by function, trade partners | loaders inside the project that uses them |

Each project README lists its sources, coverage and licence notes. Where a source cannot deliver what the
project title promises, the README says so under **Limits**. Examples: no open worldwide city price data
(project 5), central-government debt for only about half of economies (11), and trade partners for goods only
(9).

## Project shape

```
projects/NNN-slug/
├── README.md       question · data · method · findings · limits · how to run
├── app.py          Streamlit app (widgets and charts only)
├── <module>.py     analysis as pure functions, with a main() that prints the README numbers
└── tests/          unit tests and an app smoke test
```

The full conventions are in [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md).

## About

Built in public as part of a 365-day challenge. Python, pandas, statsmodels, Plotly and Streamlit. Code was
written with help from Claude (Anthropic); commits carry a co-author trailer.
