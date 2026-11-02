# Basket notes

## 2026-10-28 — First look: the weights hold tick to tick, but the gap drifts
- Hypothesis (from the first-pass analysis): FRUIT_BASKET ≈ 2·DRAGONFRUIT + 3·GRANADILLA + 1·MANGOSTEEN, so trade big gaps between the basket and its parts.
- Test: days −2..0 mids. (a) Gap = basket − (2D + 3G + M). (b) Regress basket on the components per day (levels). (c) Regress tick-to-tick basket changes on component changes (all days).
- Result:
  - The gap has mean +60 but std 484, and its daily average is −188 / +517 / −149. It is **not** a stable constant.
  - Level regressions give different weights each day (day −2: 8.7 / −0.6 / 3.4; day −1: 2.0 / 2.5 / 1.7; day 0: 1.1 / 4.9 / 0.8). Levels trend together, so these fits are unreliable.
  - Change regression: **1.79 / 2.59 / 0.93**, close to 2 / 3 / 1. The basket does move with its parts in those proportions tick to tick.
- Read: the 2/3/1 recipe is real, but the basket carries a slowly drifting premium on top of it. A fixed threshold on the gap would have been badly wrong on day −1.
- Next: trade the gap against a *rolling* mean of the gap (try a few window lengths, check each day separately), and measure how fast deviations from the rolling mean close.
- Constraint to keep in mind: every leg's limit is 40. One basket needs 3 GRANADILLA, so a full hedge covers at most 13 baskets, or 20 when hedging only DRAGONFRUIT. Decide whether to hedge fully, partially, or not at all.
- Context: liquidity is thin, at 47 basket trades and 57–75 trades per component over 3 days. Median spreads are 6 for the basket and 4 for each component.

## 2026-10-28 — Relative value fails; market-make each product on its own
- Test 1, does the gap revert to a rolling mean? z = gap − rolling mean (50 / 200 / 1,000 ticks, past only). Regressed the next 10 / 50 / 200-tick change of the basket and of 2D + 3G + M on z, each day separately. Both sides move together with similar slopes, so the gap itself barely closes, and the sign flips between days (e.g. W = 200, h = 200: basket −0.34 / +0.44 / −0.53).
- Test 2, better weights? With the change-fitted weights (1.79 / 2.59 / 0.93) the gap is still a random walk plus ~2 points of noise (variance ratio ~0.75 from 5 to 500 ticks, lag-1 −0.11). Day −2 shows the extreme: basket +1,708 against parts +119.
- Test 3, lead-lag? The same-tick correlation of basket and synthetic changes is 0.785, but every lag-1/2/5 cross-correlation either way is < 0.013, including each component on its own.
- Read: in this data the basket isn't arbitraged against its recipe. It co-moves within the tick but carries its own random-walk premium. Crossing 4 books (basket spread 6, components 4) to trade a gap that doesn't close loses money.
- Decision: no basket-vs-components trade. Each product is market-made on its own (`src/strategies/basket.py`), grid as for standalone. Rule: a product trades only if its setting made money over the 3 days under both fill rules.

  | product | setting | days −2 / −1 / 0 | official | strict |
  |---|---|---|---|---|
  | FRUIT_BASKET | EMA 0.3, no take, make 3, skew 0.3, cap 10 | 8,411 / −457 / −1,778 | 6,176 | 6,016 |
  | DRAGONFRUIT | EMA 0.3, take 6, make 1, skew 0, cap 10 | 1,379 / 1,302 / 129 | 2,810 | 3,291 |
  | MANGOSTEEN | EMA 0.3, take 6, make 3, skew 0.1, cap 10 | −679 / 996 / 664 | 982 | 820 |
  | GRANADILLA | best found: −48 official / +404 strict | | **off** | |

- Caveat for the abstract: FRUIT_BASKET's total is mostly day −2. Liquidity is thin (41–305 units traded in 3 days), so this group is about breadth, not PnL.
