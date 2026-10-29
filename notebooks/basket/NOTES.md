# Basket workstream notes

FRUIT_BASKET, DRAGONFRUIT, GRANADILLA, MANGOSTEEN (limit 40 each).
Scripts are in this folder (run them from the repo root). Charts and tables are in `outputs/basket/`.
Strategy: `src/strategies/basket.py`.

## TL;DR

- **The weights are 2 / 3 / 1** (D / G / M). Regressing basket price changes on the fruits gives 1.94 / 2.98 / 0.98 at 10 ticks and 2.02 / 2.99 / 0.84 at 500 ticks. Regressions on price levels are unreliable (they swing wildly by day), so use changes.
- **The premium (basket − NAV) is not anchored to a rolling mean.** Deviation-from-EMA signals change sign from day to day, so we have no robust short-term premium signal.
- **It is pulled slowly toward a fixed level near 0.** The slope of the future premium change on (premium − 0) is −0.11 over 1,000 ticks and −0.50 over 3,000 ticks.
- **The hedged anchored-premium strategy is positive on all 3 days but small:** +0.8k / +4.2k / +0.6k with anchor 0 and scale 1,000. Unhedged versions swing by tens of thousands on basket direction.
- **Liquidity is thin.** The basket and the fruits print only 16–25 trades a day each, so this strategy has to take liquidity, and GRANADILLA's limit caps the hedge at 13 baskets.

## Log

### 2026-10-28: weights
- **Hypothesis:** basket = 2D + 3G + 1M (from the first-pass analysis).
- **Test:** OLS of basket on fruits, in levels (per day and all days) and in 1/10/100/500-tick changes. Also compared candidate integer weights by how stable the premium is (`01_explore.py`, `outputs/basket/01_weight_regressions.csv`).
- **Result:** the change regressions agree on about 2 / 3 / 1, with R² 0.62–0.72. Levels give nonsense (day -2: 8.7 / −0.6 / 3.4) because the premium wanders, so level regressions absorb that drift. Among integer candidates, (2, 3, 1) gives the lowest premium-change std: 4.99 per tick and 42.7 per 100 ticks.
- **Decision:** use 2 / 3 / 1.

### 2026-10-28: premium behaviour
- **Result:** the premium averages −187 on day -2 (std 585), +516 on day -1 (std 136) and −149 on day 0 (std 172). Fitted to an AR(1) on all three days, it takes about 7,000 ticks to halve, which is about 0.7 of a day.
- **Basket vs NAV:** they move together at the same tick (corr 0.79), but there is **no lead-lag** (corr of NAV return to the next basket return is 0.001). The NAV doesn't tell us where the basket is going next.
- **Which leg corrects?** Relative to a rolling-1000 mean, the basket moves *with* the deviation (+0.74 over 1,000 ticks). That's momentum, not reversion, so "the gap closes" doesn't hold at these windows.
- **Day-by-day signal check** (`02_premium_signals.py`, `outputs/basket/03_premium_signal_by_day.csv`): for every EMA window and horizon tested, the correlation flips sign across days. Only W=2000 with short horizons keeps one sign, and it's weak (−0.01 to −0.16).
- **Fixed anchor:** (premium − 0) predicts the change over the next 3,000 ticks with slope −0.50. This is the one relationship that looks structural.
- **Why we think so (interpretation):** in IMC Prosperity-style basket products the premium usually reverts to a constant, and the drift we see over a few thousand ticks is noise around it. Three days is only about 4 half-lives, though, so the evidence is thin.
- **Honest caveat from chart 02:** the premium makes one slow swing, from −900 up to +900 and back down to −300. The "pull toward 0" rests on essentially one cycle. It could equally be a slow random walk that happened to come back. Treat this signal as low-confidence, and keep position size modest.

### 2026-10-28: anchored-premium strategy backtests
- **Strategy:** target basket position = −clip((premium − anchor) / scale, ±1) × max, reached by taking liquidity. Optionally hedge with −2D, −3G and −1M per basket (`03_backtests.py`, `outputs/basket/04_backtest_sweep.csv`, `outputs/basket/05_pnl_curves.png`).

| Version | d−2 | d−1 | d0 | Total |
|---|---|---|---|---|
| hedged, anchor 0, scale 1000 | +795 | +4,182 | +626 | +5,604 |
| hedged, anchor 60, scale 1000 | +1,700 | +4,089 | +231 | +6,020 |
| hedged, anchor 60, scale 600 | +1,415 | +5,906 | +214 | +7,536 |
| hedged, anchor 200, scale 600 (best on worst training day) | +5,062 | +4,820 | −966 | +8,916 |
| unhedged, anchor 0, scale 600 | −6,992 | −21,857 | +3,886 | −24,963 |

- **Why hedging matters:** unhedged, we hold up to 40 baskets of pure basket direction, and the basket's daily range is around 1,000 coins. Hedged, we only hold the premium.
- **Why it's small:** the hedge is capped at 13 baskets (3 × 13 = 39 GRANADILLA), and crossing all four books costs about 15 coins per basket each way.
- **Overfitting note:** picking by worst training day chose anchor 200, which then lost on day 0. Anchor 0 and anchor 60 (the 3-day mean) are positive every day. Anchor 0 is the least fitted choice.
- **Decision:** default to hedged, anchor 0, scale 1000.

## Open questions / next steps

1. **Use the spare basket capacity.** We hold at most 13 hedged baskets but can hold 40. Partly hedge the extra 27 (D and M have room) and measure the added risk.
2. **Market-make the four legs passively** on top, joining the touch as in standalone. Trades are thin, so expect small gains, but they count toward breadth.
3. **Execution:** we cross the full spread on every rebalance. Resting at the touch on the basket leg and only crossing the fruit legs should cut costs.
4. **Sanity-check the anchor on the official backtester.** If the day-1 premium opens far from 0, this strategy carries a big position immediately.
5. **For the abstract:** chart 02 (basket vs NAV and the premium) plus the day-by-day signal table make a clear "we tested it, here's why we only trust the fixed anchor" story.
