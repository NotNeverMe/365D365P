# 365 Projects

365 projects at the intersection of **economics, politics, philosophy and computer science**, built in public.
The rule for every project: real data or real users, a question stated up front, a check that the result is
right, and an honest page on what it cannot tell you.

Gallery and live site: **https://varad-patel.github.io/365projects/** (code: [varad-patel.github.io](https://github.com/varad-patel/varad-patel.github.io)).

This repo is a monorepo. Shared code (data loaders with caching, statistics, charts, UI helpers) lives in
[`core/`](core), and each project lives in its own folder under [`projects/`](projects) with its own README,
analysis module, Streamlit app and tests.

## Progress

Starting over. The first 15 projects were removed on 2026-10-08 (they remain in the git history) and the
list of 365 is being rewritten.

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
