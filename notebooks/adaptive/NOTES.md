# Adaptive workstream notes

Branch `rithik/adaptive` (started from `best-316k`), worked in a separate worktree so it doesn't touch `rithik/weak-products`.
Scripts are in this folder (run them from the repo root); outputs are in `outputs/adaptive/`. The research background is in `docs/research/adaptivity_and_stress_scenarios.md`.

## TL;DR

- **We built 21 "what might the judges change?" scenarios** (`src/scenarios.py`) by editing the real days, plus a mode that runs the days back to back. The edits include anchor shifts and mid-day jumps, drifts, a mirror image, volatility ×1.5/×0.6, wider spreads, broken pearl and basket rules, option vol shocks, and reshuffled days.
- **Three hard-coded facts carried almost all of `best-316k`'s scenario losses:** TOFFEE_CAKE's centre (5,000), the pearl sum (50,000) and the options' fixed 4-coin take threshold.
- **Each now adapts.** TOFFEE's and PINK's values are re-estimated on a rolling window, but only *used* once the estimate has clearly moved away (a gate). Options take wobbles that are large *relative to their recent size*.
- **The result costs nothing on the real days (+0.4k)** and raises the worst scenario by 19.4k and the scenario average by 11.6k. When TOFFEE's centre moves, the adaptive version keeps 54–55k that `best-316k` loses.

## Log

### 2026-10-30: scenario scorecard of `best-316k` (`01_scorecard.py`, `outputs/adaptive/scorecard_best316k_*`)
- **Test:** ran the full combined trader on every scenario.
- **Result:**
  - TOFFEE centre ±50 or drifting: −20 to −21% of total.
  - TOFFEE +25 or a mid-day jump: −12 to −13%.
  - Voucher wobbles 20% smaller: −20%.
  - Pearl sum moved to 50,100: −7.5%.
  - Mirror image: +0.1%, so we don't depend on trend direction.
  - Reshuffled days: +2.5 to +7.8%. Back-to-back days: +2.6%.
  - Volatility, spreads and the AMETHYST shift: within a few %.
- **Why:** the strategies trusted these three numbers completely. With TOFFEE's centre at 5,050, fair value is anchored 50 coins too low, so we keep selling a fairly priced product.

### 2026-10-30: always-adaptive versions (`02_adaptive_variants.py`)
- **Test:** re-estimate the value as a slow EMA starting at the historical value. Span sweeps: TOFFEE 500–8,000 ticks, PINK 200–5,000. The options threshold becomes max(2, k × recent std of (price − fair)), with k in 0.6–1.0.
- **Result:**
  - **Options, k = 0.8: +0.3% on the real days** and better in the worst case (66k → 79k when wobbles shrink). Free robustness, so adopted.
  - **TOFFEE:** robust (worst case ≈ 0 → 43–45k), but costs **8–13%** on the real days, because the moving anchor is noisier than the true 5,000.
  - **PINK:** robust (worst case 3.4k → 16.5k), but costs about 5% on the real days.
- **Why the cost:** this is the bias vs noise trade-off for rolling windows (Pesaran & Timmermann 2007). When nothing has changed, a rolling estimate is just a noisier version of the truth.

### 2026-10-30: gated adaptivity (`03_gated_variants.py`)
- **Idea** (change detection, after Page 1954 and Adams & MacKay 2007): keep the historical value until the rolling estimate is more than a `gate` away from it, then switch.
- **Result:**

| Version | Real days | Worst scenario |
|---|---|---|
| TOFFEE fixed 5,000 | 70.1k | −0.3k |
| **TOFFEE span 2,000, gate 20** | **70.1k (0% cost)** | **51.0k** |
| TOFFEE span 2,000, gate 15 | 68.7k (−2%) | 51.4k |
| PINK fixed 50,000 | 28.0k | 3.4k |
| **PINK span 1,000, gate 10** (gates 5–20 identical) | **28.0k (0% cost)** | **21.2k** |

- **Why it works:** on the real days the estimate never strays more than the gate, so we trade exactly as before. When the centre really moves, the estimate crosses the gate within a few hundred to a couple of thousand ticks, and the strategy follows.
- **Decision:** TOFFEE span 2,000 with gate 20; PINK span 1,000 with gate 10; options scaled threshold with k = 0.8 and a minimum of 2.
- **Overfitting caveat:** the gate values were chosen on scenarios *we* designed (shifts of 25–100). A smaller shift, around 10–15 coins, wouldn't open the gate. That costs less, but it isn't recovered.

### 2026-10-30: full comparison (`04_compare.py`, `outputs/adaptive/compare_best316k_vs_adaptive_v1.*`)
- **Real days:** 327.0k vs 326.6k. Per day it's 112,872 / 116,264 / 97,852 vs 112,084 / 113,468 / 101,042. The options threshold shifts some PnL between days.
- **Worst scenario:** 275.6k (voucher wobbles 20% smaller, where there's genuinely less edge) vs 256.2k (TOFFEE centre −50).
- **Average over scenarios:** 329.0k vs 317.4k.
- **Small costs:** within 1% on LYCHEE vol ×1.5, back-to-back days, and the reshuffles (−1 to −2.8k).

## How to score another version (for example the `rithik/weak-products` work)

From this worktree, pointing at any combined `trader.py`:

```bash
python notebooks/adaptive/01_scorecard.py path/to/trader.py --tag weak_v1
```

```bash
python notebooks/adaptive/04_compare.py adaptive_v1 weak_v1
```

## Open questions / next steps

1. **Upload `submission/trader.py` from this branch to the official site.** Expect roughly the same as `best-316k` (316k), since the real-day local totals match.
2. **Merge with `rithik/weak-products`** once that work settles. Both branches edit `standalone.py` and `pearls.py`, but in different places (TOFFEE/PINK here; JELLY/PEANUT_BUTTER/BLUE there), so conflicts should be small. Then rebuild, re-score and compare.
3. **More scenarios that don't depend on our guesses:** the structural Monte Carlo generator from the research doc, plus scenarios for judge changes we haven't imagined (TELLURIUM jump frequency, PAPER_LANTERNS bend frequency).
4. **Generic PnL safety net:** cut a module's size when its rolling PnL falls below a threshold, as a backstop for the cases we didn't think of.
