# Project guide

Every project in `projects/` follows the same shape so the repo stays easy to browse, run and test.

```
projects/NNN-slug/
├── README.md                # question, data, method, findings, limits, how to run
├── app.py                   # Streamlit app (thin: widgets + charts only)
├── <module>.py              # all analysis logic, pure functions, no Streamlit imports
└── tests/
    ├── test_<module>.py     # unit tests for the analysis functions
    └── test_<module>_app.py # smoke test: the app runs without exceptions (streamlit AppTest)
```

`<module>` must be unique across the repo (for example `gdp_growth`, not `analysis`).

## Rules

1. **Real data only.** Load through `core.worldbank`, `core.fred` or `core.bigmac`. They download once and cache
   the result under `data/`, and the cache is committed, so tests and apps run offline. If you need another
   public source, add a small loader inside your own module that follows the same cache-to-`data/` pattern.
   Never invent, interpolate silently or hard-code numbers that stand in for data.
2. **Say what the data cannot do.** Where a source cannot deliver exactly what the project title promises
   (for example city-level prices, or trade by partner), build the closest honest version and state the gap
   in the README "Limits" section and in the app footer (`core.ui.sources`).
3. **Findings in the README must be computed.** Run your module, copy real numbers out of the output, and
   give the command that reproduces them. If a number is not in the output, it does not go in the README.
4. **Analysis is separate from UI.** `<module>.py` holds pure functions that take and return pandas objects.
   Give it a `main()` that prints a short summary so `python projects/NNN-slug/<module>.py` reproduces the README.
5. **Tests are meaningful.** Unit tests use small synthetic frames with known answers (hand-computed), plus a
   couple of sanity checks against the real cached data (for example, row counts above a floor, a value you
   verified by hand). The app smoke test uses `streamlit.testing.v1.AppTest.from_file("app.py").run()` and
   asserts `not at.exception`. Tests must pass offline.
6. **Do not edit `core/`** or other projects. If you need a helper that belongs in `core/`, put it in your
   own module and mention it in your final message. (This is for a worker building one project in parallel.
   The top-level session that owns the repo may change `core/`, and must then run the whole test suite.)
7. **No git operations.** The maintainer commits. (Same scope as rule 6: the top-level session commits, one
   commit per project, message `Add #N Title`.)
8. **Network policy.** A 403/407 from the proxy is an organisation policy decision. Do not route around it.
   Report the blocked host and build the best version with the data you can reach.
9. **Browser-ready.** Every project's app also runs in the visitor's browser (Pyodide, via stlite) on the
   portfolio site, so build for that from the start. Use pandas, numpy, plotly, scipy, statsmodels or other
   packages Pyodide ships; no `subprocess`, `multiprocessing`, threads or sockets; no network access while the app
   runs (everything it needs is in the committed `data/` caches); keep one interaction under a few seconds of
   single-threaded compute; keep the data the app reads small. If the app really cannot run in a browser, say why
   in the README and tell the maintainer. See `docs/BROWSER_APPS.md` in the site repo
   (https://github.com/varad-patel/varad-patel.github.io).

## Streamlit app conventions

* Start with `core.ui.page(title, caption)`. Use `core.ui.country_picker`, `core.ui.year_range`,
  `core.ui.download` and end with `core.ui.sources(...)`.
* Pass `width="stretch"` to charts and tables (Streamlit 1.51+; `use_container_width` is deprecated).
* Charts come from `core.charts` (`lines`, `bars`, `choropleth`, `theme`) or plotly directly, then `charts.theme(fig)`.
* Wrap data loading in `@st.cache_data`.
* `app.py` imports its module with `from <module> import ...` (Streamlit puts the script's folder on `sys.path`).
* Keep the layout simple: sidebar controls, 2-4 charts, one table, one download button, sources footer.

## README template

```markdown
# NNN · Title

> One-sentence question this project answers.

## What it does
2-3 sentences. What can a user do in the app?

## Data
Table: source, indicator/series id, coverage, licence note.

## Method
Short and precise: the calculations, in plain words, with formulas where useful.

## What the data say
3-5 findings, each with a real number from running the code, and the command that reproduces them.

## Limits
Honest list: coverage gaps, definitional issues, what this cannot tell you.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/NNN-slug/app.py
    pytest projects/NNN-slug
```

## Useful sources already verified reachable

* World Bank Indicators API (through `core.worldbank`). Examples: `NY.GDP.MKTP.KD.ZG` growth, `FP.CPI.TOTL.ZG`
  inflation, `SL.UEM.TOTL.ZS` unemployment, `SI.POV.GINI`, `NY.GDP.PCAP.PP.KD`, `GC.DOD.TOTL.GD.ZS` central
  government debt, `NE.EXP.GNFS.ZS` / `NE.IMP.GNFS.ZS` trade, `PA.NUS.PPP`, `PA.NUS.GDP.PLI` (price level index).
  Browse codes at https://data.worldbank.org/indicator.
* FRED CSV endpoint (through `core.fred`): daily exchange rates `DEXUSEU`, `DEXJPUS`, `DEXUSUK`, `DEXINUS`,
  `DEXCHUS`; US CPI components such as `CPIAUCSL`, `CPIFABSL`, `CUSR0000SAH1`; policy rates `FEDFUNDS`, `ECBDFR`.
* Big Mac index (through `core.bigmac`).
* `wits.worldbank.org` and `raw.githubusercontent.com` respond from the sandbox. Check a URL before you rely on it.

Year columns from the World Bank can run to 2025 for some indicators and stop years earlier for others.
Always compute coverage (first and last year with data, share of countries covered) and show it.

FRED notes from building the first 15 projects: series ids can 404 or go stale without warning (check the last
date of every series you load), and the US CPI has no observation for October 2025, so use calendar-based
changes (`core.stats.yoy_change` is calendar-based on a DatetimeIndex).
