# CLAUDE.md

Guide for Claude Code (and anyone else) working in this repository.

## What this is

The code behind Varad Patel's **365 projects in 365 days** challenge: a Python monorepo of data dashboards, models and
simulations on economics, politics, philosophy and computer science. The portfolio site that presents them is a
separate repo, https://github.com/varad-patel/varad-patel.github.io, published at https://varad-patel.github.io
(gallery at `/365projects/`). Clone the two repos side by side, this one as `365-projects`.

Status: projects 1 to 15 (Economics × Data Science dashboards) are done, tested and pushed. Everything from 16 on is
still to build. **#50 PolicySim** is the first flagship and has a slice plan in `docs/ROADMAP.md`; it has not
been started in this repo.

## The list

The exact list of 365 projects (id, section, title, description) is `docs/CHALLENGE.tsv`. It is a copy of
`data/challenge.tsv` in the site repo, which is the authoritative one. Do not rename, reorder or drop entries.
Day 1 was 2026-10-07. The eight sections are 1 Economics × Data Science (1-50), 2 Politics × Data (51-100), 3 AI × PPE
(101-150), 4 Philosophy × CS (151-200), 5 Game Theory × AI (201-250), 6 Social Science × AI (251-300), 7 CS-heavy
(301-340), 8 Flagships (341-365).

Quality beats speed. A project is not done until it asks one question, uses real data (or real users), has tests, and has an
honest account of what it cannot show.

## Layout

```
core/                      shared code: data loaders with committed caches (worldbank, fred, bigmac), stats,
                           inequality, charts, ui, http, paths
data/                      committed caches of downloaded source data (about 8.5 MB), so everything runs offline
projects/NNN-slug/         one folder per project: README.md, app.py, <module>.py, tests/
tests/                     tests for core/
docs/PROJECT_GUIDE.md      the rules and templates every project follows (read this first)
docs/ROADMAP.md            what is next, including the PolicySim plan
docs/CHALLENGE.tsv         the list of 365
conftest.py                puts each project folder on sys.path for tests
Makefile                   setup, test, run, refresh-data
```

## Commands

```bash
pip install -e ".[dev]"            # once. Python 3.11+, streamlit>=1.51 (apps use width="stretch")
python -m pytest -q                # the whole suite, runs offline; CI runs the same
make run P=016                     # streamlit run projects/016-*/app.py
python projects/016-slug/<module>.py   # prints the numbers the README quotes
```

## Building a project

1. Read `docs/PROJECT_GUIDE.md` and the project's row in `docs/CHALLENGE.tsv`. Look at a finished project for
   the house style, for example `projects/001-gdp-growth-dashboard` and `projects/012-gdp-per-capita-explorer`.
2. Create `projects/NNN-slug/` with README, `app.py`, a uniquely named `<module>.py` and tests exactly as the guide
   describes. Reuse `core/` for loading, stats, charts and UI. Add a loader to `core/` only when more than one
   project will use it; otherwise keep it in the project's own module, following the cache-to-`data/` pattern.
3. Real data only. Download once, commit the cache under `data/`, and make the app and tests run from the cache.
   Check the last date of every series, and compute and show coverage. Never invent numbers.
4. Findings in the README are copied from real output, with the command that reproduces them.
5. Make it browser-ready (rule 9 in the guide): the app has to run in the visitor's browser through Pyodide.
6. Run the full test suite, run the app and look at it (Playwright screenshots are fine), then commit with the
   message `Add #N Title`. One commit per project. Leave Claude Code's default co-author trailer on.
7. Add the project to the progress table in `README.md` (see below), push, then register it on the site
   (next section).

### Two things that other code parses

The site importer (`scripts/import_projects.py` in the site repo) reads these, so keep their shape:

* **The project README**: a blockquote line `> One-sentence question`, a `## Data` section that names its sources, and a
  `## Limits` section whose first bullet is the main limit.
* **The progress table in this repo's `README.md`**: rows of exactly four cells,
  `| N | [Title](projects/NNN-slug) | What it answers | One finding from the data |`. The finding must be a real
  number from running the project.

### Register the project on the site

In the site repo (see its `CLAUDE.md`):

```bash
python scripts/import_projects.py --repo ../365-projects
python scripts/shoot.py --repo ../365-projects N
python scripts/build_data.py && python -m pytest -q
git add -A && git commit -m "Add project N" && git push
```

## Rules that matter most

* Real data, stated limits, computed findings, meaningful tests (the guide has the detail).
* Analysis lives in `<module>.py` as pure functions, the app is thin, and the module has a `main()` that
  reproduces the README.
* A 403 or 407 from a proxy is an organisation policy decision. Do not route around it. Say what was blocked and
  build the best honest version with the data you can reach.
* Do not bake in network access at app run time. Browser apps have none.
* Do not weaken a test to make it pass. If a number in a test was wrong, work out why before changing it.

## Using sub-agents for several projects

Building a batch in parallel works: give each worker one project, the guide, and a note that it must not touch `core/`
or other projects and must not run git. Collect the results, run the full suite yourself, read each README and look at
each app, then commit one project at a time. Treat worker reports as claims to verify, not as facts.

## Starter prompts for Claude Code

> Read CLAUDE.md and docs/PROJECT_GUIDE.md. Build project 16 (Housing Affordability Index) from docs/CHALLENGE.tsv.
> Follow the guide, make it browser-ready, run the full tests, commit it, and then register it on the site repo.

> Read CLAUDE.md and docs/ROADMAP.md. Build slice 1 of PolicySim (project 50), the engine, and stop for review
> before building the app.
