# Pearls notes

## 2026-10-28 — PINK is the sum corrector; trade it against 50,000 minus the rest
- Hypothesis: the five pearl mids sum to ~50,000, and one pearl does the correcting.
- Test: days -2..0, regressed each pearl's h-tick mid change on (sum − 50,000) for each day separately. Script and figure: `notebooks/pearls/pink_corrector.py` → [outputs/pearls/pink_corrector.png](../../outputs/pearls/pink_corrector.png).
- Result:
  - The sum is 50,000 with std 5.0 (each day: mean within ±1.1, range about ±15). Autocorrelation of the deviation is 0.94 at lag 1, 0.75 at lag 10 and 0.33 at lag 50, so a deviation lasts tens of ticks.
  - PINK absorbs the deviation: slope −0.40 at 20 ticks, −0.6 to −0.7 at 50, −0.8 to −0.95 at 100, and about −1 at 200, the same on all three days. The other four stay near 0 at every horizon.
  - Trades print only at the best bid or ask, never inside. Each pearl trades ~60 times a day at ~2 units.
- Strategy: PINK fair = 50,000 − (WHITE + BLACK + GOLDEN + BLUE mids). Cross the book when PINK is ≥ 4 through fair, and quote passively one tick inside with what's left, up to the full ±20.
- Parameter check (PINK 3-day PnL, official rule):

  | take \ skew | 0 | 0.1 | 0.3 |
  |---|---|---|---|
  | 1 | 15.0k | 1.0k | −94.8k |
  | 2 | 22.2k | 16.1k | −17.7k |
  | 3 | 25.7k | 22.1k | 7.0k |
  | 5 | 27.2k | 27.3k | 20.4k |

  Take 3–5 with no skew is a flat plateau, with every day at +8k to +9.6k. Picked 4 (mid-plateau).
- Why skew hurts: the edge *is* the position. The mispricing takes ~100 ticks to close, and leaning quotes against inventory exits early and pays the spread again. Small take edges lose because the PINK spread (4) plus noise from the other four mids eat a 1–2 tick edge.
- Final (take 4, skew 0): PINK +9,879 / +8,430 / +8,628 = **+26,937**. Under the strict fill rule it's +26,909: 6,527 units traded, only 88 of them passive, so the edge doesn't depend on the generous rule.
- Failed: market-making WHITE, BLACK, GOLDEN and BLUE around their mids (GOLDEN around an EMA, since its mid changes bounce with −0.42 lag-1 autocorrelation). 3-day PnL at position caps 3 / 5 / 10 / 20:
  - BLACK: −88 / −656 / −1,612 / −1,467
  - GOLDEN: −316 / −660 / −1,628 / −2,493
  - BLUE: −747 / −1,342 / −2,064 / −1,740
  - WHITE: +1,105 / +2,554 / +5,881 / +6,795, but mostly from day −1's drift (+5.2k at cap 20).

  They behave like random walks, nothing pulls them back, and ~60 small trades a day isn't enough spread capture to pay for the inventory risk.
- Decision at the time: the other four off. (Superseded by the breadth rule below: WHITE now trades at cap 3.)
- Idea not yet tried: GOLDEN "moves in steps" (mid changes are mostly 0 or ±0.5, flat on day −2). It might have its own pattern worth a separate look.

## 2026-10-28 — Breadth decision for the other four pearls
- Rule adopted across all groups: a product trades only if its chosen setting made money over days −2..0 under **both** the official and the strict fill rule.
- At cap 3: WHITE passes (+1,105 / +1,298, mostly day −1), so it's on at cap 3. BLACK (−88), GOLDEN (−316) and BLUE (−747) fail, so they stay off.
