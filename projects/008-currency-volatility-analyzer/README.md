# 008 · Currency Volatility Analyzer

> How volatile are exchange rates against the US dollar, when were they unstable, and how far did they fall at their worst?

## What it does
Pick currencies and a date range, then view each rate in US dollars and as an index rebased to 100. The volatility tab shades the periods flagged as unstable, using a rule and threshold you set, and lists those periods. Further tabs give the worst 30- and 90-day depreciation episodes with dates, a ranking of all 12 currencies by volatility, and a correlation matrix of returns.

## Data
Federal Reserve H.10 daily exchange rates (noon buying rates in New York) from FRED, loaded through `core.fred`. All 12 series loaded and run to 2026-10-02. FRED data are free to use with attribution.

| Currency | FRED id | FRED quote | First observation | Observations |
|---|---|---|---|---|
| Euro | `DEXUSEU` | USD per EUR | 1999-01-04 | 6,960 |
| Japanese yen | `DEXJPUS` | JPY per USD (inverted) | 1971-01-04 | 13,975 |
| British pound | `DEXUSUK` | USD per GBP | 1971-01-04 | 13,981 |
| Indian rupee | `DEXINUS` | INR per USD (inverted) | 1973-01-02 | 13,473 |
| Chinese yuan | `DEXCHUS` | CNY per USD (inverted) | 1981-01-02 | 11,421 |
| Canadian dollar | `DEXCAUS` | CAD per USD (inverted) | 1971-01-04 | 13,987 |
| Swiss franc | `DEXSZUS` | CHF per USD (inverted) | 1971-01-04 | 13,981 |
| Brazilian real | `DEXBZUS` | BRL per USD (inverted) | 1995-01-02 | 7,964 |
| Mexican peso | `DEXMXUS` | MXN per USD (inverted) | 1993-11-08 | 8,249 |
| South Korean won | `DEXKOUS` | KRW per USD (inverted) | 1981-04-13 | 11,367 |
| South African rand | `DEXSFUS` | ZAR per USD (inverted) | 1980-01-02 | 11,724 |
| Thai baht | `DEXTHUS` | THB per USD (inverted) | 1981-01-02 | 11,400 |

Every series is converted to **US dollars per one foreign unit**, so a fall always means the foreign currency depreciated.

## Method
* **Log return** between consecutive observations: `ln(rate_t) − ln(rate_{t−1})`. One-day moves quoted below are log returns. A return that spans a holiday gap covers more than one day.
* **Rolling volatility**: standard deviation of the last *w* log returns × √252, in per cent (default *w* = 30 trading days; selectable 10 to 252).
* **Instability flag**: a day is unstable when rolling volatility is *above a cut-off*. Two rules:
  * *relative* (default): the cut-off is the currency's own 90th percentile of rolling volatility over its whole history (slider 50th to 99th). "Unstable" then means unusually volatile *for that currency*, and by construction about 10% of days are flagged.
  * *absolute*: a fixed annualised volatility, default 15% (slider 3 to 40), comparable across currencies.
* **Instability periods**: runs of unstable days; runs closer than 30 calendar days are merged because a series hovering near its cut-off flips on and off.
* **Depreciation over h days** (h = 30 or 90): `rate_t / rate_start − 1`, where the start is the last rate on or before the date *h* calendar days earlier (so a window can span a few extra days over a weekend). The worst episodes are the most negative values with overlapping windows removed, so each row is a distinct episode.
* **Ranking**: annualised volatility of daily log returns over the selected years. **Correlation**: weekly (Friday-to-Friday) or daily log returns, with rates carried forward at most 5 days over local holidays.

## What the data say
Reproduce every number with `python projects/008-currency-volatility-analyzer/fx_volatility.py`.

1. **Emerging-market currencies are far more volatile than the majors.** Since 1999-01-04, the first date all 12 series exist, annualised volatility of daily returns is 16.51% for the real and 16.17% for the rand, against 11.06% (peso), 10.28% (won), 10.10% (franc), 10.00% (yen), 9.19% (pound), 9.11% (euro), 8.29% (Canadian dollar), 6.54% (baht), 6.41% (rupee) and 2.76% (yuan).
2. **The worst 90-day falls are large and mostly emerging-market.** Peso −54.6% (1994-12-09 to 1995-03-09), won −53.3% (1997-09-24 to 1997-12-23), real −45.4% (1998-12-03 to 1999-03-03), baht −35.6%, rand −35.4%. Among the large floating currencies: pound −24.2% (1992-09-01 to 1992-11-30), euro −20.2% (2008-07-29 to 2008-10-27), Canadian dollar −20.9%, yen −19.0% (1995-06-21 to 1995-09-19), franc −18.9%. Worst 30-day falls: won −45.9%, real −41.6%, peso −40.4%.
3. **One window recurs across currencies.** For 8 of the 12 currencies (real, Canadian dollar, euro, pound, rupee, won, peso, rand) one of the three worst 90-day windows ends between 2008-09-15 and 2008-12-31. This coincides with the global financial crisis of autumn 2008; it is an association in dates, not a test of cause.
4. **Other worst episodes coincide with well-known dates**, again as association only. The baht's worst 30-day window (1997-06-17 to 1997-07-17, −25.9%) contains its float on 2 July 1997, the day of its largest one-day move (log return −20.77%). The pound's worst 90-day window (1992-09-01 to 1992-11-30) contains 16 September 1992, when sterling left the exchange-rate mechanism. The real's largest one-day move (−11.44%) is 1999-01-15, when Brazil let it float. The pound's largest (−8.17%) is 2016-06-24, the day after the UK's EU referendum. The franc's largest (+13.02%) is 2015-01-15, the day the Swiss National Bank dropped its euro floor; the volatility flag counts it as instability even though it is an appreciation.
5. **The flag means different things under each rule.** With the relative rule the volatility cut-off ranges from 5.85% (yuan) to 21.83% (real), so the real is only flagged above a level well past the euro's cut-off of 12.32%. With a fixed 15% cut-off the rand is flagged on 33% of days and the real on 30%, against 12% for the peso, 11% for the franc, 2% for the euro and 1% for the Canadian dollar and yuan. The baht's longest relative-rule period runs 1997-05-20 to 1998-11-05 (535 days).
6. **Currencies move together mainly within regions and through the dollar.** Weekly return correlations since 1999: euro-franc 0.76, euro-pound 0.65, pound-franc 0.50, peso-rand 0.49. The yen is the least correlated: yen-peso −0.08, yen-real −0.04.

## Limits
* Everything is measured against the US dollar, so a "depreciation" can reflect dollar strength as much as the currency's own weakness. Percentage falls are asymmetric: a currency losing half its dollar value is a doubling in the dollar price of the currency.
* **Managed and pegged regimes** produce discrete jumps that are policy decisions, not market turbulence: the yuan's −33.6% 90-day window ending 1994-01-25 spans China's 1 January 1994 reform of its exchange-rate system, and the rupee's worst 30-day window (−20.1%, 1991-06-03 to 1991-07-03) spans India's July 1991 devaluation. The flag treats them like any other volatility.
* The relative rule flags about 10% of days *by construction*, even for a very stable currency. The percentile and the absolute level are computed over each series' whole history, so the flag is descriptive, not a real-time signal.
* Volatility is two-sided; it does not distinguish depreciation from appreciation.
* The euro exists only from 1999, so full-history comparisons favour currencies with longer samples; the ranking in finding 1 uses the common 1999 start.
* H.10 rates are noon New York quotes. Asian and European markets have already closed, so daily correlations across time zones are understated; weekly returns reduce this.
* Dates of historical events in this README come from general knowledge and are only matched to the computed windows; the code does not test causal links.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/008-currency-volatility-analyzer/app.py
    pytest projects/008-currency-volatility-analyzer
