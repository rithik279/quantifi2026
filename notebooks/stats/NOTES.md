# Statistics notes: honest error bars on everything we claimed

Branch `rithik/stats`, cut from `best-366k` (official ~366k). **Analysis only; `submission/trader.py` is unchanged.** Scripts are in this folder (run from the repo root); tables and charts are in `outputs/stats/`. Helpers (Newey-West, effective sample size, sign tests, Benjamini-Hochberg) are in `stats_lib.py`.

Motivation: every "X predicts Y" claim in the earlier notes was a correlation on per-tick, *overlapping* windows, measured separately on each of 3 days, with no standard error. Neighbouring h-tick windows share h−1 ticks, so naive significance is inflated by roughly √h. This applies the overlap-aware statistics from Rithik's internship notes (HAC lag set by the construction, effective sample size, sign tests against a naive baseline, multiple-testing correction, validated-not-fitted) to items 1–5 of the review.

## TL;DR (abstract-ready)

- **Real, by every test:** PINK's sum signal, TOFFEE_CAKE's reversion to its anchor, the PAPER_LANTERNS trend, the options book, and the TELLURIUM post-jump glide. Each beats its own naive version with t from 2.7 to 10 on 30 independent blocks, and the overlap-aware t-statistics stay large (|t| 9–54).
- **Weak:** the basket's "premium pulled toward 0" rests on an effective sample of **1.5**. Its naive t of −126 shrinks to −2.0 on 9 non-overlapping windows.
- **Not distinguishable from zero:** JELLY, PEANUT_BUTTER, WHITE, BLACK, BLUE, the basket group, and vouchers 6,800 / 7,000 / 8,100. They're kept tiny for breadth, now on a formal basis.
- **The old lead-lag filter was noise-level:** 24% of 1,144 tests passed it, against the 25% chance alone produces. With honest p-values and Benjamini-Hochberg at 5%, 20 survive. Half are a product predicting itself; the cross-product ones are all inside the pearls.
- **Leave-one-day-out:** in 9 of 10 decisions, our chosen setting does at least as well as what the procedure picks from the other two days, on every held-out day. The exception is TOFFEE, −312 net over three rotations.
- **Trials:** about 4,000 backtest configurations across the repo, plus 1,144 lead-lag hypothesis tests. Every selection above was made among those.

## 1. How much independent evidence is behind each fact (`01_evidence.py`, `outputs/stats/01_effective_sample_size.csv`)

N_eff = T (1 − ρ) / (1 + ρ), with T = 30,000 ticks and ρ the lag-1 autocorrelation.

| Fact | ρ (lag 1) | Half-life (ticks) | N_eff | Independent episodes |
|---|---|---|---|---|
| TOFFEE_CAKE deviation from 5,000 | 0.990 | 71 | **147** | the *level* 5,000: 3 days, one value |
| Pearl sum deviation from 50,000 | 0.937 | 11 | **984** | 3 days |
| Basket premium | 0.9999 | 7,083 | **1.5** | ~1 slow cycle |
| PB & J gap (JELLY − 0.41 PB) | 0.9994 | 1,217 | 8.5 | — |
| Voucher price vs smile (per strike) | ~0.99 | ~69 | ~150 per strike | 10 strikes |
| PAPER_LANTERNS trend | — | — | — | **31 trend segments** |
| TELLURIUM jumps | — | — | — | **28 spikes** |
| GOLDEN slides | — | — | — | **3 slides** |

- **Reading:** TOFFEE's *reversion* is well supported (~150 independent deviations). But the *level* it reverts to was seen in only 3 episodes, all at 5,000; that's our largest single-assumption risk, now covered by the adaptive gate. The basket's pull toward 0 really is one observation.

## 2. Honest t-statistics for the "predicts" claims (`02_honest_tstats.csv`)

Naive t (iid, overlapping windows) vs Newey-West t with lag h−1 vs plain t on non-overlapping windows (every h-th tick, averaged over staggered starts).

| Claim | h | Slope | Naive t | Newey-West t | Non-overlap t (n) | Inflation |
|---|---|---|---|---|---|---|
| PINK next-h change on (sum − 50,000) | 20 | −0.38 | −98 | **−18.4** | −22.0 (1,499) | 5.3× |
| | 50 | −0.67 | −113 | **−19.2** | −15.8 (599) | 5.9× |
| | 200 | −0.98 | −72 | **−9.2** | −4.8 (149) | 7.8× |
| TOFFEE next-h change on (mid − 5,000) | 100 | −0.44 | −92 | **−11.9** | −9.3 (299) | 7.7× |
| | 1,000 | −1.11 | −197 | **−15.7** | −5.8 (29) | 12.6× |
| LANTERNS next-h change on past smoothed change | 50 | +0.92 | 237 | **54.5** | 33.3 (598) | 4.4× |
| | 1,000 | +0.39 | 62 | 3.6 | 1.7 (28) | 17.4× |
| Basket premium next-3,000 change on (premium − 0) | 3,000 | −0.50 | **−126** | −3.9 | **−2.0 (9)** | **32×** |
| BLUE next-5 change on its last-5 change | 5 | +0.20 | 35 | 10.2 | 15.6 (5,998) | 3.4× |
| JELLY vs PB & J gap deviation | 100 | −0.03 | −5.7 | −0.7 | −0.5 (299) | 8.0× |
| | 500 | −0.50 | −39 | −2.2 | −1.8 (59) | 18× |

- **TELLURIUM glide, as an event study:** 18 jumps where the price had moved ≥ 15 coins after 20 ticks. The next 100 ticks continued the glide by **+73 coins** on average, **18 of 18 positive**, t = 12.6, sign-test p < 0.001.
- **Reading:** the core claims (PINK, TOFFEE, short-horizon LANTERNS, the glide) survive comfortably. Long-horizon claims (LANTERNS at 1,000, the basket, PB & J) shrink to marginal or nothing.

## 3. Block PnL and each edge vs its own naive version (`02_block_pnl.py`, `03_block_pnl_by_product.csv`, `03_edge_vs_naive.csv`, `03_block_pnl.png`)

30 blocks of 1,000 ticks on the `best-366k` trader (block totals reproduce the backtest: 361,364). Newey-West t of the mean uses lag 2; the sign test is one-sided against zero.

| Series | Total | Positive blocks | t | Sign-test p | Top 3 blocks' share |
|---|---|---|---|---|---|
| **TOTAL** | 361.4k | **100%** | **19.2** | <0.001 | 16% |
| TOFFEE_CAKE | 70.1k | 90% | 10.3 | <0.001 | 24% |
| PAPER_LANTERNS | 58.1k | 100% | 8.6 | <0.001 | 23% |
| TELLURIUM | 57.1k | 70% | 3.7 | 0.021 | **39%** (median block 1.0k vs mean 1.9k: jump-driven) |
| PINK_PEARLS | 28.0k | 100% | 15.1 | <0.001 | 17% |
| Options group | 130.6k | 97% | 11.3 | <0.001 | 18% |
| GOLDEN_PEARLS | 5.0k | 100% | 2.2 | <0.001 | **91%** (the 3 slides) |
| AMETHYST | 1.6k | 100% | 21.1 | <0.001 | 16% |
| Basket group | 7.9k | 43% | 1.3 | **0.65** | 96% |
| JELLY / PEANUT_BUTTER / WHITE / BLACK / BLUE | 0.4k / 0.4k / 3.2k / −0.1k / −1.0k | 33–57% | −1.9 to 2.6 | 0.29–0.98 | — |
| Vouchers 6,800 / 7,000 / 8,100 | −1.0k / 7.1k / 1.5k | 50–63% | −0.2 to 1.6 | 0.10–0.57 | — |

**Each edge vs its own naive version** (paired over the same 30 blocks):

| Edge | vs naive | Gain | Blocks better | t | Sign-test p |
|---|---|---|---|---|---|
| TOFFEE anchor | no anchor | +65.4k | 83% | **9.5** | <0.001 |
| PAPER_LANTERNS trend lead | plain EMA | +75.7k | **100%** | **6.9** | <0.001 |
| PINK sum signal | k = 0 | +22.2k | 97% | **10.0** | <0.001 |
| TELLURIUM glide | market maker without glide | +30.4k | 57% | 2.7 | 0.017 |
| TELLURIUM flow lean | plain market maker | +17.5k | 57% | 1.4 | **0.29** |
| GOLDEN slide | no slide | +4.0k | 30% (only slide blocks differ) | 1.9 | 0.011 |
| Options adaptive threshold | fixed threshold | +0.4k | 53% | 0.06 | 0.43 |

- **Reading:**
  - Three edges are overwhelming: TOFFEE, PAPER_LANTERNS and PINK.
  - The glide is significant but lumpy, as it should be for an event strategy.
  - **The TELLURIUM flow lean isn't distinguishable from a plain market maker at block level.** Its earlier support came from per-day totals.
  - The adaptive options threshold adds nothing on real days. That's expected: it's insurance for changed conditions (see the scenario scorecard), not an edge.

## 4. Multiple testing on the lead-lag scan (`03_leadlag_bh.py`, `04_leadlag_bh.csv`)

- 1,144 tests: 11 weak targets × 26 predictors × 4 horizons (1, 5, 20, 100 ticks).
- **Old filter** ("same sign on all 3 days"): 278 pass (**24%**). Pure noise gives 25%, so the filter selected nothing.
- **Honest version:** non-overlapping windows (every k-th tick), per-day correlations combined with Fisher z + Stouffer, then Benjamini-Hochberg at q = 5%. **23 pass, 20 of them also with the same sign every day.**
  - **10 are a product predicting itself:** bid/ask bounce at 1 tick, and BLUE's momentum at 5 and 20 ticks.
  - **10 are cross-product, all inside the pearls:**
    - BLUE ↔ WHITE and BLUE ↔ BLACK at 5 ticks (r ≈ −0.05 to −0.09);
    - GOLDEN ↔ WHITE at 5 and 20 ticks;
    - one weak TELLURIUM ← GOLDEN at 5 ticks (r = 0.04 / 0.01 / 0.10).
  - **None survive for PB & J, the fruits or the vouchers.** That confirms the earlier "probably noise" calls formally.

## 5. Leave-one-day-out on every parameter choice (`04_leave_one_day_out.py`, `05_leave_one_day_out.csv`)

For each held-out day, pick the config that maximises the worse of the other two days (our usual rule) from the saved sweeps. No new backtests.

| Decision | Configs | Our config's worst held-out percentile | LODO pick = ours | Ours ≥ LODO pick on held-out day | Ours − pick (3 rotations) |
|---|---|---|---|---|---|
| PAPER_LANTERNS trend | 96 | 98% | 3/3 | 3/3 | 0 |
| PINK (k, take/make, skew, cap) | 720 | 99% | 2/3 | 3/3 | +0.4k |
| Options (iv_span, take, make, cap) | 36 | 90% | 1/3 | 3/3 | +11.1k |
| TELLURIUM glide | 48 | 52% (day −2 favours other settings) | **3/3** | 3/3 | 0 |
| GOLDEN slide | 37 | 50% (no slides on day −2: all tie) | 0/3 | 3/3 | +0.0k |
| TOFFEE (span, anchor weight, take/make, skew) | 108 | 73% | 1/3 | **2/3** | −0.3k |
| Cliff fix: TELLURIUM cap 10 → 15 | 6 | 58% | 1/3 | 3/3 | +11.0k |
| Cliff fix: GOLDEN skew 5 → 2 | 4 | 62% | 0/3 | 3/3 | +0.8k |
| Cliff fix: basket min_trade 2 → 4 | 4 | 62% | 2/3 | 3/3 | +1.0k |
| Options hedge band 60 | 4 | 62% | 1/3 | 3/3 | +7.1k |

- **Strict rule** (top quartile on every held-out day, and the pick profitable on every held-out day): validates PAPER_LANTERNS, PINK and options.
- **Weaker but fairer rule for small grids:** does our choice match or beat the pick the procedure would have made without that day? Yes for 9 of 10 decisions, including all three cliff fixes, which were chosen with all days visible.
- **TOFFEE:** a slightly different setting did 1.3k better on one rotation, essentially a tie. Every candidate there makes 21–26k on the held-out day.

## What this means for the submission
Nothing needs to change in `trader.py`. The analysis gives:
- **For the abstract:** a defensible "is it real?" number for every strategy.
- **A formal basis** for keeping the noise products at tiny size.
- **Two honest downgrades to state openly:** the basket (N_eff ≈ 1.5) and the TELLURIUM flow lean (not significant on its own).

## Next steps (from the review, items 6–10)
1. **Fragility band:** treat differences inside the perturbation range as noise. For example, options hedge band 60 vs 120 and PINK k 0.5 vs 0.75, compared paired on block PnL with a Newey-West t.
2. **Options "lie detector":** split options PnL into net delta × LYCHEE move vs the remainder (pricing edge). Add a naive baseline (fair = slow EMA of each voucher's mid, no Black-Scholes) to measure what Black-Scholes actually contributes.
3. **Exponential-weighted slope for PAPER_LANTERNS** instead of the hard 100-tick window, adopted only if it passes item 5's bar.
4. **Scenario scorecard by family:** five TOFFEE variants are one family, so the worst case should weight each family once.
5. **Abstract:** order it as an argument: tested → forecasts → well formed → pays → costs → real → verdict. Use the tables above, and per-block distributions (`03_block_pnl.png`) rather than cumulative curves.

## 6. Fragility band (`05_fragility_band.py`, `06_noise_band.csv`, `06_fragility_comparisons.csv`)
- **Noise band:** 1 sd of total PnL when a random 5% of passive fills are dropped (5 seeds). Options ±1.3k and TELLURIUM ±3.6k, because both rely on passive fills. PINK ±13, PAPER_LANTERNS ±39 and TOFFEE ±29, because those take liquidity.
- **Rule:** a difference is "real" only if it exceeds 2 × the band *and* the paired block t is at least 2.
- **Chosen setting really better than the alternative:**
  - PINK k = 0.5 vs 0.25 / 0.75 / 1.0 (t 5.4 / 7.9 / 12.2);
  - PAPER_LANTERNS lead 100 vs 50 (t 5.1);
  - TELLURIUM glide wait 20 vs 40 (t 3.2);
  - options hedge band 60 vs 30 (t 4.8).
- **Noise with an ordering:**
  - options hedge band 60 vs 120 (+13.3k for 120, but t −1.2) and vs 240;
  - options iv_span 500 / 2,000 and take_k 0.6 / 1.0;
  - TELLURIUM cap 10 / 20;
  - PAPER_LANTERNS lead 200;
  - TOFFEE take_edge 5 / 10.
- **Alternative really better (borderline):** TELLURIUM glide exit "hand back to the market maker" instead of flattening: +21.0k, better in 80% of blocks, t −2.02. We chose flattening for lower inventory risk. This is the one setting the data says to reconsider. It was found with all days visible, so treat it as a candidate, not a fix.

## 7. Options lie detector (`06_options_attribution.py`, `07_options_attribution.csv`, `07_options_vs_naive*.csv`)
- **Exact split, 3 days, hedged as submitted (sums to the backtest's 130,590):**
  - pricing (vouchers converging toward fair while held): **+214.8k**;
  - entry edge (crossing the spread when we take): **−92.0k**;
  - LYCHEE direction (net delta × LYCHEE move): **+7.8k**.
- **Unhedged:** direction is −2.4k. **The book's profit is pricing, not LYCHEE direction.** The LYCHEE leg's result is noise-sized either way.
- **What Black-Scholes adds (paired, 30 blocks, all unhedged):**
  - vs fair = current mid (pure passive market making): **+192.7k**, t 7.3. Passive voucher market making alone *loses* 56.9k.
  - vs fair = slow EMA of the voucher's own mid: **+83.9k**, 63% of blocks, t 2.4. The naive EMA version makes 51.9k but isn't significant on its own (t 1.3).
- **Hedging:** −5.2k total (t −0.3, i.e. noise), but positive blocks rise from 90% to 97% and the block t from 5.7 to 11.3. It's a variance-reduction choice, as intended.
