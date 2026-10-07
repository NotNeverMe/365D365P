# 009 · Trade Balance Visualizer

> Who runs trade surpluses and deficits, how open are economies to trade, and which partners account for the flows?

## What it does
Pick economies and a range of years to see exports and imports with the balance shaded as surplus (green) or deficit (red), the balance and current account as a share of GDP, and trade openness side by side. A ranking tab lists the largest surpluses and deficits in any year, in US dollars or as a share of GDP. A partner tab shows the top trading partners, their shares, a concentration index and the bilateral balance for 18 large economies.

## Data

| What | Source and id | Coverage |
|---|---|---|
| Exports / imports of goods and services, current US$ | World Bank `NE.EXP.GNFS.CD`, `NE.IMP.GNFS.CD` | 1960 to 2025, 194 economies; 150 or more economies report through 2024 (2025 is partial) |
| Net trade in goods and services, balance of payments basis | World Bank `BN.GSR.GNFS.CD` | 200 economies, through 2024 |
| Exports / imports / trade, % of GDP | World Bank `NE.EXP.GNFS.ZS`, `NE.IMP.GNFS.ZS`, `NE.TRD.GNFS.ZS` | 194 economies, through 2024 |
| Current account, % of GDP | World Bank `BN.CAB.XOKA.GD.ZS` | 200 economies, through 2024 |
| Merchandise exports and imports **by partner** | WITS TradeStats-Trade (UN Comtrade), indicators `XPRT-TRD-VL` and `MPRT-TRD-VL`, product `Total` | 18 reporters, 1988 to 2023 (Russia 1996 to 2021), cached in `data/wits/` (1.5 MB) |

All seven World Bank codes loaded through `core.worldbank`. WITS is not in `core`, so `trade_balance.py` has its own cached loader. The request that works is the documented SDMX form, one call per reporter and flow: `https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade/reporter/usa/year/all/partner/all/product/Total/indicator/XPRT-TRD-VL?format=JSON`. A colon inside a list is rejected with HTTP 400; `all` or `;` are accepted. Regional aggregates are dropped, and the remaining partner rows sum to the WITS world total (checked in the tests). Reporters: United States, China, Germany, Japan, United Kingdom, France, Italy, Netherlands, Spain, South Korea, India, Canada, Mexico, Brazil, Australia, Russia, Turkey, Saudi Arabia.

## Method
* **Balance** = exports − imports of goods and services (national accounts basis). **Balance as % of GDP** = exports % of GDP − imports % of GDP.
* **Implied GDP** = exports ÷ (exports as % of GDP), used only to filter out very small economies from percentage rankings (default: GDP above US$50 bn).
* **Surplus/deficit shading** interpolates the exact point where the two lines cross, so the colour changes where the balance does.
* **Partner share** = partner value ÷ the reporter's WITS world total. **Bilateral balance** = merchandise exports to a partner − imports from it, both from the reporter's own statistics. **Concentration** = share of the largest partner, share of the top five, and the Herfindahl index (sum of squared shares among named partners, 0 to 10,000).

## What the data say
Reproduce every number with `python projects/009-trade-balance-visualizer/trade_balance.py`.

1. **The US deficit is by far the largest.** In 2024 the United States ran a goods-and-services deficit of US$898.5 bn (3.1% of GDP), more than three times the next seven largest deficits combined (US$289.8 bn; India −67.3 bn, Philippines −66.4 bn, Ukraine −38.8 bn). China had the largest surplus, US$548.7 bn (2.9% of GDP), followed by Ireland (254.6 bn), Singapore (206.3 bn) and Germany (177.0 bn).
2. **The US has had a trade deficit every year since 1976.** Of the 55 years with data (1970 to 2024) only four were surpluses (1970, 1971, 1973, 1975), and the longest deficit run is 49 years. The deficit was deepest relative to the economy in 2006 (−5.7% of GDP, US$786 bn) and was −3.1% in 2024. By contrast China shows a surplus in 55 of 66 years since 1960 and India a deficit in 61 of 66 (last surplus 1993).
3. **Relative to GDP, small open economies dominate the extremes.** Among economies with GDP above US$50 bn in 2024, the largest surpluses were Ireland (41.8% of GDP), Singapore (36.0%) and Luxembourg (31.8%); the largest deficits were Ukraine (−20.3%), Guatemala (−15.5%) and Uzbekistan and the Philippines (both −14.4%).
4. **Openness varies by a factor of more than ten.** Trade (exports plus imports) was 359% of GDP in Hong Kong SAR, 351% in Luxembourg and 313% in Singapore in 2024, against 25% in the United States, among economies with GDP above US$50 bn.
5. **Partner concentration differs sharply.** In 2023 Canada sent 77.3% of its merchandise exports to the United States (Herfindahl index 6,009). The United States spread its exports more widely: Canada 17.5%, Mexico 16.0%, China 7.3% (index 732). China's largest export market, the United States, took 14.8% (index 452); Germany's, also the United States, 10.0%.
6. **The two sides of a bilateral balance do not match.** The US reports a 2023 merchandise deficit of US$300.2 bn with China, Mexico US$156.8 bn and Vietnam US$109.1 bn. China's own statistics show a surplus with the United States of US$336.1 bn, US$35.9 bn more than the US figure; the two countries value and attribute trade differently (see Limits).
7. **The two balance measures mostly agree.** In 2024 exports minus imports (national accounts) and net trade in the balance of payments differ by a median 0.16% of GDP across 146 economies, but by 2.55% of GDP or more for one economy in ten.

## Limits
* **Partners are goods only and cover 18 reporters.** Services trade has no partner breakdown here; for the United States in 2023, WITS merchandise exports are 65.7% of the World Bank's goods-and-services exports. WITS ends in 2023 and has nothing for Russia after 2021. The goods balance in WITS (US 2023: −US$1,150 bn) is not comparable with the goods-and-services figures from the World Bank; never add them.
* WITS imports are generally valued including freight and insurance and exports without, and bilateral statistics are as each reporter reports them (no mirror-data adjustment), which is why partner balances differ between the two countries involved.
* Taiwan appears in UN Comtrade as "Other Asia, nes", and Unspecified and Special-category trade have no partner; the last two are left out of partner rows (but kept in the world total that shares are measured against).
* Balance-as-%-of-GDP rankings reward very small or financially special economies. Ireland's, Luxembourg's and Singapore's trade is widely attributed to multinational companies and re-exports, so a surplus of 30% to 40% of GDP does not mean what it would for a manufacturer like Germany.
* The World Bank's 2025 values exist for only about 138 economies, so the app and README use 2024 as the latest full year. Exports minus imports (national accounts) and net trade (balance of payments) are different compilations; the app shows both for the selected economy.
* A trade deficit is not by itself a sign of weakness or a measure of unfair trade; it is the counterpart of capital inflows and saving-investment gaps, which this project does not analyse.

## Run it
    pip install -e .            # once, from the repo root
    streamlit run projects/009-trade-balance-visualizer/app.py
    pytest projects/009-trade-balance-visualizer
