# UTEFA QuantiFi 2026 — Team #21 — Strategy Abstract

**Team members:** _[ADD NAMES]_

## 1. Summary

One `Trader.run()` trades all 26 products with four strategy families. Every family is built on a **structural reason to trade**: a relationship we can name and test, such as "the five pearls sum to 50,000" or "PAPER_LANTERNS moves in straight-line segments". We did not keep parameters just because they scored well.

| | Day −2 | Day −1 | Day 0 | Total |
|---|---|---|---|---|
| Local backtest (our replica of the official fill rule) | 163,932 | 168,616 | 154,828 | **487,376** |
| Official site (previous version, same strategies minus two small changes) | | | | **~484k** |

Our local engine matched the official site within about 1% on the previous version (483.2k local vs ~484k official). Earlier versions also tracked it closely (326.6k local vs 316.1k official; 361.4k vs ~366k), so we trust local numbers as estimates of official ones.

| Family | Products | 3-day PnL | Edge |
|---|---|---|---|
| Options | LYCHEE + 10 vouchers | 188.9k | Volatility-smile fair value, market making around it |
| Single products | AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM, JELLY, PEANUT_BUTTER | 250.3k | Anchor reversion, trend following, post-jump drift |
| Pearls | 5 pearls | 40.2k | Sum-to-50,000 rule, GOLDEN plateaus |
| Basket | FRUIT_BASKET + 3 fruits | 7.9k | Hedged premium reversion (low confidence) |

## 2. Process (applied to every product)

1. **Explore:** price paths, spreads, autocorrelation and variance ratios, where trades print relative to the book, and whether aggressive traders are informed (does the price keep moving their way after they trade?).
2. **Name a structural reason** to trade. If none exists, trade tiny for breadth only.
3. **Shared engine:** estimate a fair value, *take* any quote priced through fair by a margin, otherwise *quote at* the best bid/ask, with quotes shifted against inventory. Every order is sized from the current position so that possible fills can never breach a position limit.
4. **Replica backtester** of the official fill rule (resting orders fill when a historical trade prints at our price or better), unit-tested against the wiki's examples.
5. **Out-of-sample parameter choice:** sweep, choose on two days (ranking by the *worse* day), score the third. Leave-one-day-out over every major decision.
6. **Honest statistics:** overlapping-window t-statistics were inflated 4–30×, so every claim was re-tested with Newey-West errors, non-overlapping windows, effective sample sizes, and Benjamini-Hochberg correction across 1,144 lead-lag tests.
7. **Stress tests:** synthetic days built by editing the real days (Section 5).

**Key microstructure fact:** every historical trade prints at or beyond the touch, never inside the spread. Under the official rule, quoting exactly *at* the best bid/ask catches every fill at the best available price. Improving by a tick wins no extra fills and gives away a coin per fill.

## 3. Strategies and the evidence behind each

### Options: LYCHEE and vouchers (188.9k)
- **Model:** every tick, back out each voucher's implied volatility in *total* volatility (σ√T), so we never need the calendar time to expiry. Fit a vega-weighted quadratic smile across strikes, smooth its coefficients over ticks, and price each voucher off the smile with Black-Scholes. Then market-make around that fair value and take quotes ≥ 3 through it.
- **Hedging:** the book's net delta is hedged by *leaning* LYCHEE quotes toward the hedge position rather than crossing the spread. An early version that hedged tightly lost 94k to LYCHEE's spread.
- **Evidence:** 97% of 1,000-tick blocks were profitable (t = 11.3). Each strike's price wanders about ±5 coins around the smile and partly reverts (~30% within 50 ticks), and that is what we harvest.
- **Removed:** an informed-flow nudge (reading `market_trades`) added +2.8k locally but **about −30k on the official site**, because the site delivers `market_trades` differently from our replica. The final trader reads no market trades for any decision, so its results do not depend on that delivery.

### TOFFEE_CAKE (80.7k)
- **Finding:** reverts toward 5,000 (half-life ~70 ticks; ~150 independent deviations). It has the widest spread, and its aggressors tend to be wrong.
- **Strategy:** fair = blend of a fast EMA (span 5) and the anchor (weight 0.4); take when price is ≥ 9 through fair.
- **Adaptive guard:** the anchor is re-estimated as a slow EMA that starts at 5,000 and only replaces it once the estimate is > 20 away. This costs nothing on the real days and protects us if the level moves.
- **Evidence:** +65k vs the same strategy with no anchor, better in 83% of blocks (t = 9.5). Leave-one-day-out: every candidate setting made 21–26k on the held-out day.

### PAPER_LANTERNS (60.1k)
- **Finding:** moves in straight-line segments hidden under quote noise (31 segments). The smoothed 50-tick change predicts the next 50 ticks (slope +0.92, Newey-West t = 54).
- **Strategy:** fair = EMA + slope × 100 ticks, so we hold a position in the trend's direction.
- **Evidence:** +76k vs a plain EMA, better in **100%** of blocks. Our setting ranked in the top 2% of 96 configurations on every held-out day.

### TELLURIUM (103.7k)
- **Finding:** about 10 jumps a day, and the price keeps drifting in the jump's direction afterwards (18 of 18 qualifying jumps continued, +73 coins on average, t = 12.6).
- **Strategy:** a jump is a 3-tick move larger than 5.5× local volatility. Local volatility is measured with bipower variation, which a single jump barely inflates. Wait 20 ticks to confirm the direction, hold the full limit in that direction, and exit 250 ticks after the jump.
- **Adaptive guard:** every signal is also paper-traded, and new trades are skipped while fewer than 3 of the last 6 signals made money. On the real days it never fires. If the post-jump drift reversed on every jump (stress test), it cuts the loss from −101.7k to −59.4k.
- **Lesson:** our first TELLURIUM sweep **overfit** (+15k/day in training, −23k on the held-out day). That is why every later choice was made out of sample.

### PINK_PEARLS and the pearl family (40.2k)
- **Finding:** the five pearl mids sum to 50,000 (std 5; N_eff ≈ 980), and PINK is the pearl that closes the gap (slope −0.98 over 200 ticks).
- **Strategy:** PINK fair = mid − 0.8 × (sum − 50,000). The signal is dropped if the sum's moving average drifts more than 40 from 50,000 (the rule has broken).
- **Adaptive closer (what if the role moves to another pearl?):** every tick we estimate, from past data only, each pearl's slope of its 20-tick change on the sum deviation 20 ticks earlier. On days −2..0, PINK's slope is −0.35 to −0.41 every day and every other pearl's is between −0.07 and +0.09. The sum signal goes to whichever pearl's slope is below −0.25; the current closer keeps the role while its slope stays below −0.1 (hysteresis), and if no pearl qualifies, all pearls fall back to plain market making. PINK is the prior during a 1,000-tick warm-up. **Real days: identical PnL. Stress test with the closer role moved to BLACK / BLUE / WHITE: +34.3k / +32.2k / +15.8k, vs +4.1k / −11.1k / −14.5k for the fixed-PINK version.**
- **Evidence:** PINK makes 28.1k, profitable in 100% of blocks (t = 15.1), and +22k vs the same strategy without the sum signal.
- **GOLDEN_PEARLS** sits on 50-coin plateaus. We quote around the current plateau and ride the slides between them (3 slides, 5.0k).
- **WHITE, BLACK and BLUE** have no predictive signal that survives multiple-testing correction, so they are small EMA market makers.

### Basket (7.9k, low confidence)
- **Finding:** basket ≈ 2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN. The premium swings ±900 slowly.
- **Strategy:** hold baskets against the premium, hedged with the fruits (max 13 baskets, set by GRANADILLA's limit), and rebalance only on changes of ≥ 4 baskets.
- **Honest caveat:** the pull toward 0 rests on an effective sample of **1.5** (one slow cycle). Its naive t of −126 shrinks to −2.0 on non-overlapping windows. It is kept small and hedged; unhedged versions swung by tens of thousands.

### AMETHYST, JELLY and PEANUT_BUTTER (5.9k)
AMETHYST is a fixed-value (10,000) market maker. JELLY and PEANUT_BUTTER are random walks with no edge we could find (the JELLY–PEANUT_BUTTER pair's honest t is −0.7). They get a minimal quoter: 5 lots at the touch around a 5-tick EMA, quoted only on the side where the touch is beyond fair, with position held to about ±2. Out of seven stress scenarios (volatility ×1.5 and ×0.6, a wider spread, mirrored prices, reshuffled blocks), it beat our earlier capped market maker in all seven.

## 4. What did not work (and why)
- **Tight delta hedging (−94k):** crossing LYCHEE's spread to hedge cost more than the delta risk. Leaning quotes toward the hedge fixed it.
- **Informed-flow signals on `market_trades`:** real in our data, but the official engine delivers trades differently. The voucher nudge flipped from +2.8k to about −30k, so it was removed everywhere.
- **Lead-lag scan:** 24% of 1,144 tests passed our first "same sign every day" filter, against the 25% pure noise produces. After honest p-values and Benjamini-Hochberg, only pearl-internal and self-predictive effects survive, so nothing was traded on cross-product lead-lag.
- **TELLURIUM first sweep:** overfit; fixed with inventory caps and, later, replaced by the post-jump drift strategy.
- **PB & J pair (JELLY vs PEANUT_BUTTER):** looked like a cointegrated pair, but the honest t is −0.7. Not traded.

## 5. Robustness

Day 1 is unseen, so each edge that depends on a single structural fact has a guard. Every guard is **free on the real days** (identical PnL) and limits the damage if that fact changes. Each was tested on synthetic days made by editing the real ones, so the book shapes and trade flow stay realistic.

| Assumption that could break | Guard | Stress test | Without guard | With guard |
|---|---|---|---|---|
| PINK is the pearl that closes the 50,000 gap | Online "closer" detector (Section 3) | Closer role moved to BLACK / BLUE / WHITE | +4.1k / −11.1k / −14.5k | **+34.3k / +32.2k / +15.8k** |
| The pearls sum to 50,000 | Drop the signal if the sum's average drifts > 40 away | Sum moved to 50,100 | — | falls back to plain market making |
| TELLURIUM drifts after a jump | Paper-trade every signal; stop while < 3 of the last 6 won | Drift removed / reversed on every jump | −101.7k | **−59.4k** |
| TOFFEE_CAKE reverts to 5,000 | Gated adaptive anchor (slow EMA starting at 5,000, used once > 20 away) | Centre moved to 5,050 | large losses with a fixed anchor | follows the new centre |
| The site delivers `market_trades` like our replica | No decision reads `market_trades` | Official site vs local | flow nudge: +2.8k local → ~−30k official | local ≈ official (483k vs 484k) |

**Other checks:**
- **Position limits:** zero orders cancelled for limits on all three days. Every order is sized from the current position.
- **Fill stress:** taking-based edges (TOFFEE_CAKE, PAPER_LANTERNS, PINK, options takes) barely move when passive fills are halved. TELLURIUM jump-drift and the options book are the most fill-sensitive (noise band ±3.6k and ±1.3k when 5% of passive fills are dropped at random).
- **Statistics (measured on our earlier 361k version, same core edges):** total PnL was positive in 100% of 30 independent 1,000-tick blocks (t = 19.2), and the top 3 blocks supply only 16% of it.
- **Leave-one-day-out:** in 9 of 10 major parameter decisions, our setting matched or beat what we would have chosen without the held-out day.
- **Breadth:** all 26 products are traded every day. Products with no edge we could prove (JELLY, PEANUT_BUTTER, WHITE, BLACK, BLUE) are market-made at small size, and we say so rather than claim an edge.

## 6. Final submission
The final file combines the best version of each family from our team's branches: the volatility-smile options book and TELLURIUM jump-drift, the anchor and trend market makers for TOFFEE_CAKE and PAPER_LANTERNS (re-tuned by leave-one-day-out), the pearl sum rule, and the hedged basket. Each family runs inside its own `try` block, so an error in one never stops the others. All state lives in `traderData` as compact JSON, and only `json`, `math`, `typing` and `datamodel` are imported.
