# Robustness notes: parameter sensitivity, fill stress, combined trader

Branch `rithik/robustness` merges the four workstreams so every strategy can be tested together. Scripts are in this folder (run from the repo root); charts and CSVs are in `outputs/robustness/`. Background on methods and papers: `docs/research/overfitting_and_synthetic_data.md`.

## TL;DR

- **Most of our PnL sits on broad plateaus.** PAPER_LANTERNS, options, TOFFEE_CAKE (given its anchor), PINK and TELLURIUM all keep most of their PnL when a parameter moves one notch, on every day.
- **The biggest single assumption is TOFFEE_CAKE's anchor of exactly 5,000.** Moving it 25 coins cuts that product's PnL by half to two thirds, and 50 coins removes the edge entirely, though it ends near break-even rather than a big loss. Our day-split test *can't* catch this, because all three days share the same anchor.
- **We found and fixed three choices sitting next to cliffs:**
  - basket `min_trade` 2 → 4 (a value of 1 loses on every day);
  - GOLDEN `skew` 5 → 2 (a value of 10 loses);
  - TELLURIUM `soft_cap` 10 → 15 (the centre of the 10–20 plateau).
- **Stricter fills barely matter except for TELLURIUM and AMETHYST.** Total PnL drops 8% even if only trades strictly *through* our price fill us. Options, PAPER_LANTERNS, TOFFEE_CAKE, PINK and the basket earn by *taking*, which the fill rule doesn't affect. TELLURIUM falls from 23.5k to 4–8k.
- **The options time-to-expiry issue is negligible.** Assuming day 1 on every historical day changes options PnL by 0.1k out of 130k.
- **The combined `submission/trader.py` reproduces the sum of the four groups exactly.** After the fixes it makes **112,084 / 113,468 / 101,042** (total 326,594) locally.

## Log

### 2026-10-30: one-at-a-time sensitivity (`01_param_sensitivity.py`)
- **Test:** for 13 tuning units (each standalone product, each pearl, the basket group, the whole options book), move one parameter at a time across a grid around the chosen value, keep the rest fixed, and backtest days −2..0. 220 backtests. Charts: `01_sensitivity_{standalone,pearls,basket,options}.png` (blue = total, grey = each day, red dot = chosen). Table: `01_sensitivity_summary.csv`.
- **Robust (neighbours within ~10%, every day positive):**
  - PAPER_LANTERNS: lead 50–400, span 10–50 and slope window 50–200 all give 53–59k.
  - Options: iv_span 500–2,000, take_edge 3–4, make_edge, skew and min_price are all flat. PnL scales with `soft_cap` (10 → 31k, 25 → 64k, 50 → 130k). That's capacity, not fragility.
  - TOFFEE_CAKE: span, take_edge, make_edge and skew are all flat (67–77k).
- **Sensitive:**
  - **TOFFEE_CAKE anchor:** 4,950 → 3.9k, 4,975 → 26.6k, **5,000 → 70.1k**, 5,025 → 35.4k, 5,050 → −0.3k. Mirror-image reading: if day 1's true anchor moved 50 coins, this product would go to about zero, not to a large loss.
  - **PINK k:** 0 → 5.8k, 0.25 → 18.5k, **0.5 → 28.0k**, 0.75 → 23.2k, 1.0 → 15.1k, 1.5 → 1.1k (with take_edge fixed at 1). The heatmap shows higher k works if take_edge rises with it.
  - **TELLURIUM soft_cap:** 3 → 4.6k, 5 → 8.5k, 10 → 23.5k, 15 → 26.7k, 20 → 25.5k, 40 → 20.9k. The old choice of 10 was at the edge of the plateau.
  - **Basket min_trade:** 1 → **−17.6k (negative every day)**, 2 → 5.6k, 4 → 7.9k, 8 → 9.9k (but 0 on day 0). Rebalancing on every one-basket wiggle in the target means crossing four spreads over and over.
  - **GOLDEN skew:** 0 → 1.2k, 2 → 1.1k, 5 → 1.0k, 10 → −1.1k.
- **Noise products** (JELLY, PEANUT_BUTTER, WHITE/BLACK/BLUE pearls): PnL jumps around between ±3.5k with no pattern. That confirms there's no edge, and it's why they stay at tiny size.

### 2026-10-30: 2D heatmaps (`02_heatmaps.py`, `outputs/robustness/02_heatmaps.png`)
Each cell shows total PnL and, in brackets, the worst single day. The chosen point is boxed.
- **PINK (k × take_edge):** a diagonal ridge. Stronger signals need a higher take threshold. The chosen point (0.5, 1) is inside the ridge. (0.75, 3) and (1.0, 5) are equally good, so the edge doesn't rely on one exact setting.
- **PAPER_LANTERNS (lead × slope_window):** a broad green plateau. Only the corner where a long lead extrapolates a very short slope window loses (lead 400, window 25 → −17k). The chosen point is central.
- **TOFFEE_CAKE (anchor_w × take_edge):** with anchor_w = 0 there's no edge (≈0 for every take_edge). With any weight ≥ 0.25 it's 44–76k. The edge *is* the anchor, which matches the 1D finding.
- **TELLURIUM (flow_beta × soft_cap):** the good region is flow_beta ≥ 0.4 with soft_cap 10–20. With no flow signal it's weak and gets worse with size (cap 40 → −8k, worst day −21k). This confirms the flow signal is what makes larger size safe.
- **Basket (anchor × scale):** everything is small (2–9k total), with worst days around −2k to +1k. There's no region of strong, reliable edge, which matches its low-confidence label.
- **Options (iv_span × take_edge):** a plateau over iv_span 500–2,000 and take_edge 2–4 (113–130k, worst day 31–40k). The chosen point (1000, 4) is the best cell and sits inside the plateau. Very slow IV (4,000) does badly on days −2/−1 because the EMA starts from the first tick and needs time to settle.

### 2026-10-30: fill stress (`03_fill_stress.py`, `outputs/robustness/03_fill_stress.png`, `03_fill_stress_summary_k.csv`)
- **Test:** re-run every unit with stricter fills: a random 75% / 50% / 25% of eligible historical trades fill us (2 seeds each), or only trades strictly *through* our price fill us. These numbers use the parameters from before the three fixes.

| Unit (total over 3 days, k) | official rule | 75% | 50% | 25% | through only |
|---|---|---|---|---|---|
| Options book | 130.2 | 130.9 | 131.8 | 131.4 | 132.4 |
| TOFFEE_CAKE | 70.1 | 69.6 | 69.7 | 69.5 | 69.4 |
| PAPER_LANTERNS | 58.1 | 57.8 | 57.6 | 57.4 | 57.3 |
| PINK_PEARLS | 28.0 | 28.0 | 27.9 | 27.8 | 27.8 |
| TELLURIUM | 23.5 | 20.3 | 6.0 | 8.4 | 4.2 |
| Basket group | 5.6 | 5.6 | 5.6 | 5.6 | 5.6 |
| AMETHYST | 1.6 | 1.2 | 0.8 | 0.4 | 0.0 |
| **TOTAL** | **321.0** | **315.9** | **301.3** | **302.6** | **296.6** |

- **Why:** the big earners take liquidity when the price is far enough from fair value. Taking fills against the visible book, so it doesn't depend on the generous passive-fill rule. In options, removing passive fills slightly *raises* PnL, so passive voucher fills are about break-even and the taking does the work. TELLURIUM and AMETHYST are pure market-making and are the only units whose numbers we can't trust until the official site confirms the fill rule.
- **Time to expiry:** with the options trader assuming scoring day 1 on every historical day, which is what the site will do, options make 130.1k versus 130.2k. It doesn't matter, because each strike's IV is implied with the same (wrong) time, so the errors cancel.

### 2026-10-30: fixes applied
| Change | Why | Before (d−2 / d−1 / d0) | After |
|---|---|---|---|
| basket `min_trade` 2 → 4 | 2 sits next to a cliff (1 loses every day) | 795 / 4,182 / 626 | 1,589 / 5,283 / 1,036 |
| GOLDEN `skew` 5 → 2 | middle of the 0–5 plateau, away from 10 (loses) | 134 / 152 / 702 | 142 / −38 / 960 |
| TELLURIUM `soft_cap` 10 → 15 | centre of the 10–20 plateau | 6,440 / 8,160 / 8,893 | 10,649 / 7,342 / 8,704 |

These were chosen with all three days visible. They are robustness moves (towards the middle of a plateau), not new optimisation, but count them as in-sample.

### 2026-10-30: combined trader (`tools/build_trader.py` → `submission/trader.py`)
- **What the build script does:** inlines each strategy file with prefixed names (every file has its own LIMITS/PARAMS), then adds a `Trader` that runs every group each tick. Each group keeps its own memory in its own slot of `traderData`, and one group crashing can't stop the others.
- **Check:** `python src/backtester.py submission/trader.py` gives 112,084 / 113,468 / 101,042, equal to the sum of the groups. The output passes pyflakes (no undefined names).

### 2026-10-30: official-site check of the combined trader
- **Test:** uploaded `submission/trader.py` (rebuilt after the three fixes) to https://www.utefa.com/quantifi.
- **Result:** **316,088 total** over days −2..0, versus **326,594 locally: 3.2% lower.** Read off the site's chart (approximate): about 103k / 120k / 93k per day, versus 112k / 113k / 101k locally. The lowest point was −947, at the very start. The curve rises steadily with no large drawdowns.
- **Why it matters:** our local fill model is close to theirs, so the local numbers, sweeps and robustness results all carry over. A 3% gap is about what we'd expect from small engine differences, such as queue handling and whether `traderData` and positions carry across days. The site plots one continuous curve, but we don't know whether it resets between days.
- **Next:** upload each group file separately to see where the ~10k gap sits. The candidates are TELLURIUM and AMETHYST, the only fill-sensitive units.

## Open questions / next steps

1. **The TOFFEE_CAKE anchor (most important):** test an adaptive anchor, such as a very slow EMA starting at 5,000. Check how much PnL it keeps on real data and how it behaves on data with the anchor shifted. Also decide as a team whether 5,000 is structural; like AMETHYST's 10,000, it looks like an organizer-chosen round number.
2. **CSCV / probability of backtest overfitting:** record PnL per 2,500-tick block in the sweeps and compute PBO per workstream (see the research doc).
3. **Structural Monte Carlo** for the three assumptions that carry the most PnL: the TOFFEE_CAKE anchor, PAPER_LANTERNS kink frequency, and LYCHEE realized vol.
4. **Official-site calibration** (`submission/README.md`): if their fills are stricter, TELLURIUM and AMETHYST are the products to re-tune. The rest should hold.
