# Options notes

## 2026-10-28 — Price each voucher off LYCHEE with its own smoothed implied vol
- Setup: Black-Scholes with r = 0, time in days (8 days to expiry at the start of day −2), implied vol per strike from the mid by bisection. Figure: `notebooks/options/smile.py` → [outputs/options/smile.png](../../outputs/options/smile.png).
- Facts (days −2..0):
  - LYCHEE realized vol is 0.0181 / 0.0182 / 0.0184 per √day, very stable. It mildly mean-reverts (variance ratio 0.73 at 1,000 ticks).
  - The smile has the same shape every day: wings higher (6800 ≈ 0.024, 7500 ≈ 0.019, 8100 ≈ 0.021 on days −2/−1). Implied vol is above realized everywhere. Day 0 sits ~10% higher across all strikes.
  - Spreads: 3 for 7200+, 6 for 6800/7000. ~1,700 trades per strike.
- Test: fair_k = BS(S, K, T, EMA of strike k's own implied vol, using past ticks only). Residual = mid − fair. Regressed the delta-hedged voucher move over the next 1 / 10 / 50 ticks on the residual.
  - At EMA α 0.002 the residual std is 2–6, and 20–30% of it closes within 50 ticks, on every strike.
  - A faster EMA (0.2) gives a smaller residual that closes faster (−0.1 to −0.6), but it's mostly noise around the mid.
- Strategy (`src/strategies/options.py`): fair value as above, quoted with `market_make` (take 3, make 1, no skew, cap 50 per strike). Net voucher delta is hedged by crossing the LYCHEE book only when it drifts more than 150 from the LYCHEE position.
- Time to expiry: the trader can't see the day, so it always assumes day 1 (5 days at its start). In backtests on days −2..0 this costs nothing measurable, because each strike's implied vol is fitted with the same T that prices it, so the error cancels.
- Grid (voucher + LYCHEE 3-day PnL, official rule):
  - IV EMA α: 0.0005 → 41–71k (big swings by day: a vol-level bet), **0.002 → 115–127k**, 0.01 → 72–87k.
  - Take edge at α 0.002: 2 → 127k, 4 → 115k, 8 → 20k.
  - Hedge band: 20 → 87k (LYCHEE −28k, pure spread cost on 14,871 units), 60 → 101k, **150 → 125–142k**, 250 → 133–135k, never → 115k.
  - Every combination of take 2–3 with band 100–250 lands between 110k and 142k. Picked take 3, band 150 (middle of both ranges).
- Final: vouchers 7000–8100 + LYCHEE = **+135.5k official, +137.6k strict**. Nearly all fills come from crossing the book, so the fill rule doesn't matter. Per strike (official): 7000 +5.0k, 7200 +13.1k, 7300 +24.2k, 7400 +32.3k, 7500 +20.7k, 7600 +22.5k, 7750 +9.5k, 7900 +4.8k, 8100 +1.1k. LYCHEE +2.4k.
- Failed / off: **VOUCHER_6800** lost on days −2 and −1 (−3.9k, −6.3k) and only won on day 0 when implied vol jumped (−2.9k total). Deep in the money, it has almost no time value, so its "fair value" is mostly LYCHEE plus noise. Off. **VOUCHER_7000** has the same pattern (−2.0k, −5.5k, +12.6k) and only passes the rule because of day 0. It's the most fragile strike.
- Why it works (our read): the voucher books don't re-price instantly or consistently with LYCHEE and with each other. A slowly-updated, per-strike vol gives a fair value that's stable enough to lean on, and the passive flow is large.
- Risk: a smoothed vol lags a sudden vol-level change (as on day 0). If day 1 has a big vol shift, the strikes will all be wrong in the same direction at once. The hedge band and the per-strike cap of 50 limit the damage.
- Not tried: fitting a smile curve across strikes (only a per-strike vol); selling vol outright on implied > realized (one-day horizon, too exposed to vol-level moves); market-making LYCHEE on its own beyond the hedge.

## 2026-11-01 — Market-making LYCHEE with its spare limit: failed, dropped
- Hypothesis: LYCHEE's limit (200) is mostly unused (only the hedge touches it), and its mid mildly mean-reverts (variance ratio 0.73), so quoting it inside the spread around an EMA could add profit like TOFFEE_CAKE and PAPER_LANTERNS.
- Test: when the position was within the hedge band, quote one tick inside the spread around an EMA of the mid, leaning toward the hedge target. Grid: EMA α 0.3 / 0.05 / 0.01 × make 1 / 2 × lean 0.02 / 0.05 / 0.1 × size 10 / 30 per side (36 settings), compared day by day with the current version under both fill rules.
- Result: no setting improved every day under both rules. The best one by worst day changed PnL by +2,595 / −531 / −1,104 (official) and −514 / +385 / −690 (strict). Others swung up to ±5–7k on a single day, with no consistent sign.
- Why: there's almost no flow to make markets into. LYCHEE printed only ~170 trades in three days, and sizes 10 and 30 gave identical results, so the size limit never bound. The PnL changes come from shifting how much LYCHEE we hold (marked to a random-walking mid), not from earning the spread.
- Decision: removed. The trader is back to the uploaded version (+208,996 locally, all three days unchanged).

## 2026-11-01 — One smile across strikes beats a vol per strike: kept (+51k)
- Hypothesis: smoothing each strike's implied vol separately lets one noisy strike drag its own fair value off. Fitting one curve across all strikes uses every strike's price to set each one's vol, so fair value should be steadier. It also slides along the curve as LYCHEE moves, instead of keeping each strike's old vol.
- Method: every tick, take the implied vol of every voucher with usable time value. Fit vol = a + b·x + c·x² by least squares, where x = 100·ln(K/S)/√T (moneyness). Smooth (a, b, c) with an EMA. Each voucher's fair value = Black-Scholes at the smoothed curve's vol for its strike. Everything else is unchanged (take 3, make 1, cap 50, 6800 off, hedge band 150). Standard library only (3×3 normal equations, Cramer's rule).
- Test: options products only, day by day, against the per-strike version, under both fill rules. Tested in a scratch copy first; the repo only changed after it passed.

  | smile smoothing α (take 3) | gain per day, official | total official | total strict |
  |---|---|---|---|
  | 0.002 | +24.1k / −7.1k / +5.8k | +22.9k | +15.7k |
  | 0.01 | +22.5k / +2.5k / +15.7k | +40.7k | +37.1k |
  | **0.02** | **+26.6k / +2.9k / +21.6k** | **+51.1k** | **+50.9k** |
  | 0.05 | +22.1k / +4.5k / +15.4k | +42.0k | +40.0k |
  | 0.1 | +20.7k / +2.1k / +17.0k | +39.8k | +39.4k |
  | 0.2 | +26.8k / −0.9k / +12.6k | +38.5k | +35.8k |

  - At take 3, every α from 0.01 to 0.1 gains on every day under both rules, a flat plateau. Picked 0.02 (about 50 ticks of memory), mid-plateau.
  - Take 2 also gains every day at α 0.02 (+48.7k). Take 4 is weaker and loses on day −1 at several α.
  - Adding a slow per-strike correction on top of the curve (α 0.002) was worse at every smile speed (+5.7k to +11.7k, with losing days), so the curve stands alone.
- The gain is broad: 7 of 9 traded strikes improve (7000 +12.4k, 7500 +10.7k, 7400 +9.0k, 7600 +7.0k, 7300 +6.9k, 7750 +6.4k, 7900 +4.7k). VOUCHER_7200 gives back −2.5k and the LYCHEE hedge −3.7k.
- Final options group: **+186,546 official / +188,504 strict** (was +135,465 / +137,568). The LYCHEE hedge is −1,299 official / +309 strict. It's risk control for the vouchers, not a profit strategy, so it's judged as part of the options group rather than by the per-product rule.
- Why it works (our read): the smile's shape is stable (see the smile chart), so most of a single strike's vol move from tick to tick is noise. Pooling all strikes filters that noise. The ~50-tick smoothing still follows real level shifts (like day 0's ~10% rise) much faster than the old ~500-tick per-strike EMA did.
- Risk unchanged in kind: a sudden vol-level jump still misprices all strikes together for a while. The faster smoothing shortens that window.
