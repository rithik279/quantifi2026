# Pearls workstream notes

WHITE, BLACK, GOLDEN, PINK, BLUE_PEARLS (limit 20 each).
Scripts are in this folder (run them from the repo root). Charts and tables are in `outputs/pearls/`.
Strategy: `src/strategies/pearls.py`.

## TL;DR

- **The five mids sum to 50,000.** Mean 49,999.9, std 5.0, and every day agrees (std 4.65–5.29). PCA says the constraint has equal weights (1.00 / 1.00 / 1.01 / 0.99 / 1.00).
- **PINK is the one that corrects the sum.** Its future move ≈ −k × (sum − 50,000), with k ≈ 0.38 at 20 ticks, 0.67 at 50 and 0.98 at 200. The other four don't react (slopes near 0).
- **Trading PINK around `mid − 0.5 × (sum − 50,000)` makes about 9–10k a day, every day**, including day 0, which we held out. Without the signal (k = 0), the same engine makes about 2k a day.
- **GOLDEN sits on plateaus** (8,000 / 7,900 / 7,800 / 7,750, with ±0.5 noise). Market-making around the plateau level is small but positive every day.
- **WHITE, BLACK and BLUE have no edge yet.** We keep them in the book with tiny size (soft cap 5) for breadth. BLUE trends and loses a little under market-making.
- **Current total: +10.3k / +10.7k / +10.1k** on days -2 / -1 / 0.

## Log

### 2026-10-28: the sum constraint
- **Hypothesis:** the five pearls are tied by a conservation rule (from the first-pass analysis).
- **Test:** sum of mids, per-day stats, autocorrelation, and PCA on levels (`01_explore.py`, `outputs/pearls/01_mids_and_sum.png`).
- **Result:** sum = 50,000 ± 5. Its smallest PCA eigenvalue is 4.9 versus 700+ for the next, with weights ≈ 1 each. The deviation is persistent but mean-reverting: autocorr 0.94 at lag 1, 0.75 at lag 10 and 0.33 at lag 50.
- **Decision:** treat 50,000 as a hard anchor.

### 2026-10-28: who closes the gap?
- **Test:** regress each pearl's future mid change on (sum − 50,000) at horizons of 1–200 ticks (`outputs/pearls/02_who_corrects_slope.csv`).
- **Result:** PINK's slope is −0.03 / −0.13 / −0.38 / −0.67 / −0.98 at 1 / 5 / 20 / 50 / 200 ticks. All other pearls stay under ±0.1 up to 50 ticks.
- **Why it works (our read):** the simulation seems to hold the sum fixed by nudging PINK. When the others move, PINK absorbs the change over the next ~50–200 ticks. That makes PINK predictable from the other four.
- **Decision:** PINK fair value = mid − k × (sum − 50,000).

### 2026-10-28: how strong should the PINK signal be? (sweep)
- **Test:** sweep k ∈ {0, 0.3, 0.5, 0.7, 1.0, 1.3} together with the market-making settings. Pick by the worst of days -2/-1 and check day 0 (`02_param_sweep.py`, `outputs/pearls/06_param_sweep_all.csv`, `outputs/pearls/08_pink_pnl_by_k.png`).

| k | d−2 | d−1 | d0 (held out) |
|---|---|---|---|
| 0 (no signal) | 3,366 | 842 | 1,813 |
| 0.3 | 8,845 | 6,955 | 8,717 |
| **0.5 (chosen)** | **10,029** | **8,930** | **9,089** |
| 0.7 | 9,900 | 8,799 | 9,235 |
| 1.0 | 9,788 | 8,756 | 9,074 |

- **Result:** anything from 0.5 to 1.0 works, so the result isn't sensitive to the exact k. That's a good sign it isn't overfit. Taking at 1 coin of edge and quoting at the touch with no skew does best.
- **Decision:** k = 0.5, take_edge 1, make_edge 0.5, skew 0, full 20 limit.

### 2026-10-28: GOLDEN plateaus
- **Result:** the mid sits at 8,000.0 (7,925 ticks), 7,800, 7,900 or 7,750, plus ±0.5 noise. The lag-1 autocorr of its returns is −0.42 (pure quote noise), and plateaus are short (≤15 ticks at an exact value), so the noise is constant.
- **Strategy:** fair value = nearest multiple of 50 when the mid is within 0.5 of it, otherwise the mid.
- **Result:** +134 / +152 / +702, positive but small. GOLDEN only trades about 60 times a day.

### 2026-10-28: WHITE, BLACK, BLUE
- **Correlations:** WHITE and BLACK tick returns correlate at −0.68, and BLUE at −0.25 with each. These are contemporaneous with no lead-lag (|corr| < 0.03), so they can't be traded as a signal.
- **Market-making results:** WHITE is noisy but positive with cap 5 (+558 / +2,154 / +496). BLACK is about 0. BLUE loses with every setting tried (−0.4k to −1.4k a day).
- **Why BLUE loses (our read):** its variance ratio is 1.66, so it trends. Momentum at 20 ticks is +0.06 to +0.12 on every day and reverses by 500 ticks. Trends run over a market maker's inventory.
- **Risk finding:** WHITE + BLACK + BLUE ≈ 50,000 − GOLDEN − PINK, which moves slowly. Holding equal positions in all three halves the risk (100-tick change std 11.5 vs 22.9 for WHITE alone). This is the basis for hedging inventory across pearls.

## Open questions / next steps

1. **Hedge inventory across pearls.** Market-make WHITE, BLACK and BLUE as a group, skewing each one's quotes by the group's net position rather than its own. The sum constraint should let us run bigger size at the same risk.
2. **BLUE momentum:** try a small trend-following overlay at the 20-tick horizon instead of plain market-making.
3. **PINK refinements:** use microprice or the touch for the other four instead of the mid, and try a horizon-aware k (bigger when the deviation is old).
4. **Check on the official backtester** that PINK's PnL survives. It's the single biggest robust edge we've found so far.
5. **For the abstract:** `01_mids_and_sum.png`, `05_pink_vs_implied.png` and `08_pink_pnl_by_k.png` tell the full story: hidden rule → who enforces it → what it's worth.

### 2026-10-30: robustness follow-up (`rithik/robustness`, see `notebooks/robustness/NOTES.md`)
- **GOLDEN `skew` 5 → 2.** Skew 0 / 2 / 5 / 10 → 1.2k / 1.1k / 1.0k / −1.1k, so 5 sat next to a losing value. Result: 142 / −38 / 960.
- **PINK heatmap (k × take_edge):** a diagonal ridge, so a stronger signal needs a higher take threshold. (0.5, 1), (0.75, 3) and (1.0, 5) are all ~27–28k, so the edge doesn't depend on one exact setting.
- **Fill stress:** PINK is unaffected (28.0k → 27.8k with only through-price fills), because it earns by taking.
