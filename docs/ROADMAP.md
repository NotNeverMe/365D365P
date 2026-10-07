# Roadmap

## Where the repo is

Projects 1–15 (the economics × data science dashboards) are done. They produced a reusable base: data
loaders with committed caches, a Gini and Lorenz toolkit (`core/inequality.py`), growth and price-level
calculations, and a house style for apps and READMEs.

## Next: #50 PolicySim, the first flagship

> What happens to income, inequality and government revenue when you change a tax-and-transfer policy, and
> which value judgement (utilitarian, Rawlsian, libertarian) makes a policy look good?

PolicySim is built in slices, each one shippable on its own. The first slice is the engine; the app, data
calibration for more countries and the behavioural layer follow.

### Slice 1: the engine (started)

* **Synthetic population calibrated to published data.** No household microdata is in the repo, so the
  population is generated from a distribution fitted to a country's World Bank quintile income shares and
  Gini (`SI.DST.*`, `SI.POV.GINI`) and mean income (GDP per capita). The fit is validated: the simulated
  population must reproduce the published quintile shares within a stated tolerance.
* **Policies as data.** A policy is a small declarative object: income-tax brackets, flat tax, a universal
  basic income, a means-tested transfer, a consumption tax. Policies compose and can be compared.
* **Outcomes.** Revenue and cost, disposable income, effective tax rate by decile, Gini before and after,
  Palma ratio, poverty rate against a relative line, and the budget balance.
* **Welfare lenses.** Utilitarian (sum of utility, with a stated concavity), Rawlsian (welfare of the worst
  off) and libertarian (minimal redistribution constraint) summaries, so the same policy is scored three ways.
* **Assumptions page.** Every assumption (population model, utility function, no behavioural response yet)
  is listed in the README and the app, with a sensitivity table showing how results move if they change.
* **Tests.** Hand-computed tax cases, budget identities (revenue minus transfers equals the balance), and
  calibration checks against the committed World Bank data.

### Slice 2: behaviour and trade-offs

Labour-supply response through an explicit elasticity parameter, with the Laffer-style revenue curve and a
sweep showing how the answer depends on the elasticity. Efficiency versus equality frontier.

### Slice 3: platform

More countries, saved scenarios, side-by-side comparison, a write-up of method and limits. Reuses the engine
for #35 Inequality Simulator and #38 Tax Revenue Simulator.

## Principles that carry through

Stated assumptions beat hidden ones. A model says "under these assumptions, it estimates", never "it
predicts". Every result a README quotes is reproduced by a command.
