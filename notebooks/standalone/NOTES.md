# Standalone workstream notes

AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS (limit 50), TELLURIUM (40), JELLY, PEANUT_BUTTER (50).
Scripts are in this folder (run them from the repo root). Charts and tables are in `outputs/standalone/`.
Strategy: `src/strategies/standalone.py`, one market-making engine with a different fair value per product.

## TL;DR

| Product | What it is | Strategy | d−2 | d−1 | d0 |
|---|---|---|---|---|---|
| AMETHYST | Pinned at 10,000 | Market-make around 10,000 | 527 | 608 | 478 |
| TOFFEE_CAKE | Reverts to ~5,000, spread 15 | Fair = blend of EMA10 and 5,000; take ≥ 8 through fair | 24,080 | 24,774 | 21,245 |
| PAPER_LANTERNS | **Piecewise-linear trend** under bid/ask noise | Fair = EMA + slope × 100 ticks (trend-following) | 19,769 | 19,496 | 18,786 |
| TELLURIUM | Informed flow + ~10 jumps/day of ~170 | Market-make, fair shifted by recent signed flow; inventory cap 10 | 6,440 | 8,160 | 8,893 |
| JELLY | Random walk | Tiny market-making (cap 3), for breadth | −766 | 742 | 426 |
| PEANUT_BUTTER | Random walk | Small market-making (cap 10), for breadth | −320 | 712 | −23 |
| **Total** | | | **49,730** | **54,492** | **49,804** |

These numbers come from our local backtester (`src/backtester.py`), which copies the official fill rule. Section "Caveats" covers why live PnL will be lower.

## The one structural fact everything builds on

**Every historical trade prints at or beyond the best bid/ask, never inside the spread** (`01_explore.py`, section 3). Under the official rule, a resting order fills when a trade prints at our price or better, *at our price*. So:
- quoting **at the touch** catches every trade at the best possible price;
- pennying (quoting one tick inside) gives up edge and gains no fills;
- quoting behind the touch gets almost no fills (TELLURIUM is the exception, since 28% of its trades sweep past the touch).

The real engine's queue priority isn't modelled, which is part of why this backtest is optimistic.

## Log

### 2026-10-28: first look (`01_explore.py`)
- **Stats** (`outputs/standalone/02_stats.csv`):
  - AMETHYST's mid only ever takes the values 9,999.5, 10,000 and 10,000.5.
  - TOFFEE_CAKE has a spread of 15 and a variance ratio of 0.45 (mean-reverting, half-life ~71 ticks).
  - PAPER_LANTERNS' lag-1 return autocorrelation is −0.50, meaning the mid is mostly quote noise.
  - TELLURIUM trades 1,225 times a day, versus 45–143 for the others.
- **Adverse selection** (`07_adverse_selection.png`): after an aggressive TELLURIUM trade the mid moves +2.7 the next tick and +6.4 within 20 ticks in the trade's direction, more than its half-spread of 4.9. So naive market-making on TELLURIUM loses. TOFFEE_CAKE is the opposite: aggressors there are wrong (−4 by 500 ticks).
- **Fair-value candidates:** the "wall mid" (the price level with the biggest volume) is worse than the plain mid for every product here. Unlike some Prosperity products, there's no hidden fixed-offset bot.

### 2026-10-28: TELLURIUM flow (`02_tellurium_flow.py`)
- **Result:** trade direction persists. The next trade is on the same side 82% of the time. Strong 5-tick signed flow, *as seen one tick later* (what we can actually act on), predicts a ±4.6 move over 20 ticks. That's about the half-spread, so not enough to pay for taking, but enough to decide which side to quote. Book imbalance and microprice don't help.
- **Decision:** shift the fair value by 0.8 × the decayed signed flow, and stay passive.

### 2026-10-28: first strategy and diagnostics (`03_strategy_diagnostics.py`)
- The first version made +55k, but PAPER_LANTERNS lost 17.6k and TELLURIUM swung −14.5k / −3.2k / +23k.
- **Split by fill type:**
  - TELLURIUM's taking fills lost 7.8 per unit, and its passive fills earned 6.5 at fill time but only +0.65 by 100 ticks later.
  - TOFFEE_CAKE's big profit wasn't a bug. It comes from taking at deviations around 5,000: we sold 1,298 units at an average of 5,013 and bought 1,248 at 4,992. The payoff takes longer than 100 ticks, so short markouts understate it.

### 2026-10-28: parameter sweep, and how it overfit (`04_param_sweep.py`)
- **Method:** sweep each product alone, pick by the worst of days -2/-1, report day 0 as out-of-sample.
- **What went wrong:** TELLURIUM and JELLY picks made +15–18k a day in training and **lost about 23k on day 0**. Their PnL was inventory riding a random walk, not edge. With a limit of 50 and daily moves of ±100, inventory noise (±5,000) dwarfs spread capture (~900/day).
- **What held up:** AMETHYST and TOFFEE_CAKE (anchor 5,000 with weight 0.5) were stable on all three days.
- **Lesson for the abstract:** a walk-forward check is what caught this.

### 2026-10-28: inventory control (`05_inventory_control_sweep.py`)
- **Change:** added `soft_cap` (max position we build), switched to passive-only, and ranked by the worst of all three days plus how much daily PnL varies.
- **TELLURIUM:** flow signal + cap 10 → +6.4k / +8.2k / +8.9k, with the smallest day-to-day spread (std 1.3k). Every top setting uses the flow signal. Bigger caps make more on average but swing ±10k.
- **JELLY and PEANUT_BUTTER:** no setting makes money reliably, so they're random walks with no edge. We keep them at tiny size so we still trade every product.
- **Selection caveat:** TELLURIUM's cap of 10 was chosen with all three days visible. The pure walk-forward pick (cap 25) still made +3.6k on day 0.

### 2026-10-28: shapes the stats missed (`06_shapes_lanterns_tellurium.py`, `01_price_paths.png`, `14_lanterns_trend_tellurium_jump.png`)
- **PAPER_LANTERNS** moves in straight-line segments with kinks. After smoothing out the bid/ask noise, the past 50-tick change predicts the next 50-tick change with **correlation +0.79 / +0.82 / +0.82** on the three days. The typical slope is 33 coins per 1,000 ticks. The negative tick-level autocorrelation was just quote bounce hiding the trend.
- **TELLURIUM** jumps about 10 times a day by a median of 165 coins. Nothing predicts a jump in the 20 ticks before it. Afterwards it drifts +15 further over 100 ticks, then reverts −45 by 500 ticks. Jumps are what wipe out market-making inventory, which is why capping inventory helps so much.

### 2026-10-28: PAPER_LANTERNS trend fair value (`07_lanterns_trend_sweep.py`)
- **Strategy:** fair = EMA20 + (slope over 100 ticks) × lead. With a large lead, the fair value sits past the touch in the trend's direction, so the engine takes and holds a position with the trend.

| Best for each lead | d−2 | d−1 | d0 |
|---|---|---|---|
| 0 (plain EMA) | 3,487 | 3,550 | 1,275 |
| 25 | 16,308 | 12,493 | 12,090 |
| **100 (chosen)** | **19,769** | **19,496** | **18,786** |
| 300 | 19,541 | 19,498 | 18,665 |

- **Result:** lead 100–300 is a flat plateau, so the result isn't sensitive to the exact setting. PAPER_LANTERNS went from −17.6k to +58k.
- **Why it works:** we hold ±50 in the trend's direction and only lose at the kinks, which happen every ~500–2,000 ticks.

## Caveats

- **The fill model is generous.** Every trade at the touch fills us, ahead of any queue. Expect lower live PnL, especially for market-making-heavy products (AMETHYST, TELLURIUM). Taking-based edges (TOFFEE_CAKE, PAPER_LANTERNS) depend less on this.
- **TOFFEE_CAKE assumes the 5,000 anchor holds on day 1.** If it shifts, the strategy keeps buying a falling price up to the limit. An adaptive anchor (a very slow EMA) is worth testing.
- **PAPER_LANTERNS** profits from trends continuing. A day with many kinks, or none, would change the result a lot.

## Open questions / next steps

1. **Calibrate the backtester:** upload `src/GivenScripts/example_trader_3.py` to the official site. We get 527 / 608 / 478 for days −2 / −1 / 0; if theirs differs, our fill model is off.
2. **TOFFEE_CAKE:** compare a fixed 5,000 anchor against a slow adaptive anchor for robustness. Pass on the anchor-weight question to whoever owns the abstract.
3. **PAPER_LANTERNS:** detect kinks, using a faster slope estimate or a stop-out when the trend's sign flips.
4. **TELLURIUM jumps:** after a jump, hold a small position with it for ~100 ticks, then fade it. There are only 30 jumps in the data, so be careful about overfitting.
5. **Merge:** this file is self-contained. The take/make engine is copied in `pearls.py` and `options.py`, so deduplicate it when building the final `trader.py`.

### 2026-10-30: robustness follow-up (`rithik/robustness`, see `notebooks/robustness/NOTES.md`)
- **TELLURIUM `soft_cap` 10 → 15.** The cap sweep (3 / 5 / 10 / 15 / 20 / 40 → 4.6k / 8.5k / 23.5k / 26.7k / 25.5k / 20.9k) showed 10 was at the edge of the plateau. Result: 10,649 / 7,342 / 8,704.
- **TOFFEE_CAKE's anchor is the biggest single assumption:** 4,950 / 4,975 / 5,000 / 5,025 / 5,050 → 3.9k / 26.6k / 70.1k / 35.4k / −0.3k. A 50-coin shift removes the edge (≈0), but doesn't turn it into a big loss.
- **Fill stress:** TOFFEE_CAKE and PAPER_LANTERNS don't change, because they earn by taking. TELLURIUM (23.5k → 4–8k) and AMETHYST (1.6k → 0–1.2k) depend on the fill rule.
