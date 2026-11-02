# Team progress log

Where the whole project stands, in one place. Details and evidence for each group live in `notebooks/<ws>/NOTES.md`. Update the status table when something changes, and add a dated entry to the log at the bottom.

**Due:** Nov 1, 11:59 PM, `submission/trader.py` + abstract (≤ 5 pages) via the Google Form.

**How we're working:** each teammate builds a full trader for every product on their own branch. At the end we take the best version of each product group. The numbers below are Selena's branch (`selena/infra`).

## Status (Selena's branch)

| Group | Traded | Off (no edge) | 3-day PnL official / strict | Notes |
|---|---|---|---|---|
| options | LYCHEE (hedge), VOUCHER 7000–8100 (9 strikes) | VOUCHER_6800 | 186,546 / 188,504 | [options](options/NOTES.md) |
| standalone | AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM, JELLY, PEANUT_BUTTER | — | 35,522 / 30,827 | [standalone](standalone/NOTES.md) |
| pearls | PINK, WHITE (cap 3) | BLACK, GOLDEN, BLUE | 28,043 / 28,207 | [pearls](pearls/NOTES.md) |
| basket | FRUIT_BASKET, DRAGONFRUIT, MANGOSTEEN | GRANADILLA | 9,968 / 10,127 | [basket](basket/NOTES.md) |
| **total** | **21 of 26** | 5 | **260,078 / 257,664** | |

- Per day (official): +95.5k / +82.9k / +81.6k (was +68.9k / +80.1k / +60.1k before the smile fit). Chart: [outputs/pnl_by_group.png](../outputs/pnl_by_group.png).
- "Strict" = `--match worse`: resting orders only fill on trades strictly worse than our price. The total barely moves, because most PnL comes from crossing the book (options, PINK).
- **Breadth rule:** a product trades only if its chosen setting made money over days −2..0 under both fill rules. That's why 5 products are off; each failure is explained in its group's notes.
- All settings were picked in-sample on these 3 days (no held-out day). We favoured settings that are positive every day and whose neighbours are also positive, over the single best number.

## Ranked by how much we trust it
1. **PINK_PEARLS** (+26.9k): a structural rule (sum = 50,000, PINK corrects), the same on every day, independent of the fill rule.
2. **Options** (+186.5k): the smile fit gains on every day at every smoothing speed tested from 0.01 to 0.1, and 7 of 9 strikes improve. Main risk: a sudden vol-level jump on day 1.
3. **AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS**: positive every day.
4. **TELLURIUM, DRAGONFRUIT**: positive overall, with one weak day each.
5. **Weakest:** JELLY, PEANUT_BUTTER, MANGOSTEEN, WHITE, FRUIT_BASKET (mostly one day), VOUCHER_7000 (only day 0) and VOUCHER_8100.

## Official site checks (utefa.com/quantifi)
- ✅ **Current version (smile fit) confirmed 2026-11-01:** official backtester **+260,118** over days −2..0 vs **+260,078** locally (≈ 0.02% apart), lowest point −1,195, peak 261,192. Screenshot: [outputs/official_backtest_2026-11-01.png](../outputs/official_backtest_2026-11-01.png), cropped for the abstract as [outputs/official_backtest_chart.png](../outputs/official_backtest_chart.png).
- Earlier version, for the record:
- ✅ **Scores match.** Uploaded `submission/trader.py` on 2026-10-28: the official backtester ends at **210,077** over days −2..0, vs **208,996** locally (≈ 0.5% apart). Its curve bottoms at −1,112 near the start of day −2 and climbs steadily. The official chart runs the three days as one continuous curve, while ours restarts each day flat, which likely explains the small gap.
- Screenshot of the official run: [outputs/official_backtest_2026-10-28.png](../outputs/official_backtest_2026-10-28.png). For the abstract, crop it to the chart and pair it with [outputs/pnl_by_group.png](../outputs/pnl_by_group.png), which shows where the PnL comes from.
- ✅ **Voucher symbols are `VOUCHER_*`.** Options are ~135k of the total; with the wrong names the total would be ~73k.
- ✅ **It runs:** no import, time or `traderData` problems (ours: standard library only, ~0.4 ms per tick, `traderData` ≤ 631 characters).
- Note: the site shows "trader.py submitted successfully" after an upload. That is the **backtester** upload, not the competition entry. The final entry is the Google Form (team lead, abstract + `trader.py`, by Nov 1, 11:59 PM).

## Next steps
1. Compare with teammates' branches product group by product group (same backtester, both fill rules), and keep the best of each.
2. Oct 31: freeze the code. Draft the abstract from the NOTES files and the three charts (`outputs/pearls/pink_corrector.png`, `outputs/options/smile.png`, `outputs/pnl_by_group.png`).
3. Nov 1: submit early via the Google Form.

## Log

### 2026-11-01 — Options: one smile across strikes, +51k (Selena + Claude)
- Replaced each strike's own smoothed vol with one smile curve fitted across all strikes every tick (quadratic in moneyness, smoothed over ~50 ticks). It gains on every day under both fill rules at every smoothing speed from 0.01 to 0.1, with 7 of 9 strikes improving. Total now **+260,078 official / +257,664 strict** locally (was +208,996). Details in [options notes](options/NOTES.md).
- Re-uploaded: the official backtester gives **+260,118** (local +260,078). The abstract's numbers, options section, risks and both PnL charts are updated to this version.

### 2026-11-01 — Tried LYCHEE market-making; dropped (Selena + Claude)
- Quoted LYCHEE inside the spread with its spare limit, 36 settings. None improved every day under both fill rules; changes were noise of ±1–7k per day. LYCHEE has ~170 trades in three days, too little flow to earn a spread. Removed; trader unchanged at +208,996 locally. Details in [options notes](options/NOTES.md).
- Abstract drafted as a shared doc: summary, method, one section per group, risks, four charts.

### 2026-10-28 — Rest of the book on Selena's branch (Selena + Claude)
- **Standalone:** profiled the five remaining products. TOFFEE_CAKE and PAPER_LANTERNS mean-revert, the other three are random walks. TELLURIUM's informed flow is real but gone by the time we can see it (one tick later), so it isn't a signal; we quote it wide and small. Book imbalance and microprice predict nothing. Market-made all five around a mid or EMA, with settings chosen for stability. +33.9k on top of AMETHYST.
- **Basket:** the 2/3/1 recipe holds tick to tick, but the basket-vs-parts gap is a random walk that doesn't revert to a rolling mean, and neither side leads. So there's no relative-value trade; each product is market-made on its own with small caps. GRANADILLA is off. +10.0k.
- **Options:** the smile is stable day to day, and implied vol is above LYCHEE's realized vol (0.018). Priced each voucher off LYCHEE with its own slowly smoothed implied vol, quoted around that price, and hedged net delta loosely (only past 150). A tight hedge just paid the spread (−28k). VOUCHER_6800 is off. +135.5k.
- **Pearls:** adopted the breadth rule. WHITE is on at cap 3, BLACK, GOLDEN and BLUE off.
- **Shared code:** moved the take-then-quote logic into `common.market_make`, and added `--products` and data caching to the backtester.
- Full trader: **+209.0k official / +206.7k strict**. Charts: [smile](../outputs/options/smile.png), [PnL by group](../outputs/pnl_by_group.png).

### 2026-10-28 — Infra, AMETHYST, PINK (Selena + Claude)
- **Data first look (all products, days −2..0):** AMETHYST mid is pinned at 10,000. The pearl sum is 50,000 (std 5). TELLURIUM has 3,675 trades vs 50–430 for other non-vouchers. Vouchers trade ~1,700 times each. Median spreads range from 3 (AMETHYST, GOLDEN, most vouchers) to 15 (TOFFEE_CAKE). Basket's fixed-weight gap drifts by day (see basket notes).
- **Built the shared infra** so everyone can work in parallel and merge into one file: local backtester with the official fill rule plus a strict mode, a trader skeleton with a `traderData` slice per strategy, crash isolation and a limit safety net, and a build script that pastes everything into `submission/trader.py` and rejects non-stdlib imports and name clashes. Checked against the given AMETHYST examples (+1,612.5) and edge cases.
- **Key finding for everyone:** the given AMETHYST examples make 0 under the strict rule, because all their fills were trades at exactly their price. We should always report both numbers.
- **AMETHYST:** quote half the size at 9,998/10,002 and the rest at 9,999/10,001. That matches the best official result (+1,612.5) and keeps +556 under the strict rule.
- **Pearls:** PINK alone closes the gap between the sum and 50,000 (≈ 90% within 100 ticks, every day). Trade PINK against 50,000 − the other four: +26.9k, nearly all from crossing the book. Skewing against inventory hurts, because the position has to be held while the gap closes.
- Evidence chart: [outputs/pearls/pink_corrector.png](../outputs/pearls/pink_corrector.png).
