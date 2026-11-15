# Hybrid notes

## 2026-11-01: final submission choice (v9)
- **Hypothesis:** a teammate's latest file (v7_2, official ~484k) beats our hybrid (465k local); the best submission takes it as the base and adds whatever we still do better.
- **Test:** local backtest of every candidate in `submission/other_people_code/` on days −2..0, then a per-product comparison.
  - Results: v7_2 483,159 · v7 486,037 · ours 465,178 · trader_4 440,850 · trader_v4 436,576 · trader_1 (was `trader (1).py`) 260,078.
  - v7 is only higher because its voucher flow nudge reads `market_trades`, which the official site delivers differently (about −30k there).
- **Result:** v7_2 beats us on TOFFEE_CAKE (+10.6k, re-tuned span 5 / anchor_w 0.4 / take 9 / skew 1), PAPER_LANTERNS (+2.0k), the pearl market makers (+4.9k) and TELLURIUM (+1.2k). Options, basket and AMETHYST are identical. We only win PEANUT_BUTTER (+870), so v8 = v7_2 with our PEANUT_BUTTER market maker.
- **Adaptive pearl closer (v9):** each pearl's 20-tick change regressed on the sum deviation 20 ticks earlier. PINK is −0.35..−0.41 every day; the others are −0.07..+0.09.
  - The first version (span 1,000, threshold −0.2, no hysteresis) **lost 14k on the real days** by flipping away from PINK on short windows.
  - Span 3,000, switch at −0.25 and keep the current closer while its slope is below −0.1: identical on the real days (40,190).
  - Swap-scenario totals with v9 (vs v8): BLACK closer +34.3k (+4.1k), BLUE +32.2k (−11.1k), WHITE +15.8k (−14.5k).
- **Decision:** submit v9 = `submission/trader.py` (484,029 local, no limit cancellations).

## 2026-11-01 (later): v10 = v9 + trader_4's JELLY / PEANUT_BUTTER quoter
- trader_4 (440.9k overall) wins JELLY (+2.1k vs 0.5k) and PEANUT_BUTTER (+2.1k vs 0.4k) with a minimal quoter: 5-tick EMA fair, 5 lots at the touch only on the side beyond fair, stop adding at |position| ≥ 5% of the limit.
- It also "wins" FRUIT_BASKET and LYCHEE alone, but those are hedge legs inside their groups, so they were not swapped.
- JELLY + PB stress (v9 → v10): real 892 → 4,239; vol ×1.5 36 → 5,584; vol ×0.6 1,557 → 2,030; spread +1 2,141 → 2,916; mirror 892 → 4,239; bootstrap 972 → 1,598 and 6,858 → 8,134. Better in all 7.
- **Decision:** submit v10 (487,376 local, no limit cancellations).

## 2026-11-14: pre-merge review of all rithik/* branches
- **Check:** `Team21_Trader.py` reproduces 487,376 locally with no orders cancelled for limits, and so does each `src/strategies/*.py` file on day 0. The backtester tests pass 10/10.
- **Finding, options hedge:** the LYCHEE "hedge" is a quote skew (3 coins at a soft cap of 40). On days −2 and 0, the vouchers' net delta reaches about 110 while LYCHEE never holds more than 20, and most strikes end the day at ±50. **Why it matters:** the book carries most of its delta, so call it "hedge-skewed", not "delta-hedged". It also contradicts our risk-first story if we oversell it.
- **Finding, silent errors:** the final file's `except Exception: pass` around each family hides failures (no `<group>_error` in v10).
- **Decision:** the submitted file stays untouched (it's the record of what we sent). The limitations are documented in `submission/README.md`, and `tools/build_trader.py` now writes `submission/trader_built.py` so a rebuild can't overwrite the submission. Duplicate archive files were removed: `trader_v7 (1).py` (same as `trader_v7.py`), and `sim_ratio.py` (Jeffery's copy is at the repo root on main). `trader (1).py` was renamed `trader_1.py`.
