# Options workstream notes

LYCHEE (limit 200) and VOUCHER_6800 … VOUCHER_8100 (10 strikes, limit 50 each). The data uses `VOUCHER_<strike>`, not the wiki's `LYCHEE_VOUCHERS_<strike>`.
Scripts are in this folder (run them from the repo root). Charts and tables are in `outputs/options/`.
Strategy: `src/strategies/options.py`.

## TL;DR

- **Time to expiry:** 8 days at the start of day −2, so **5 days at the start of scoring day 1**. The engine never tells the trader the day, so `options.py` defaults to day 1. The local backtester calls `set_day()`.
- **Each strike's implied vol is stable; its price isn't.** Prices wander about ±5 coins around what that strike's own slow IV implies, and about 30% of the gap closes within 50 ticks.
- **Strategy:** fair = Black-Scholes(S now, K, T, *slow EMA of that strike's own IV*). We market-make at the touch, take at ≥ 4 coins through fair, and delta-hedge with LYCHEE only when the net delta drifts more than 60 from target.
- **Result: +46.2k / +44.0k / +40.0k** on days −2 / −1 / 0, with day 0 held out. Vouchers trade about 560 times a day each, so there are lots of fills.
- **Hedging style matters.** A tight hedge (band 10) crossed about 43k LYCHEE units and lost 94k, almost all of it spread. A wide band (60) cuts the average net delta from 101 to 35 at the same PnL.
- **Options are priced rich.** ATM IV is 1.90–2.14% per √day, versus realized vol of about 1.6% per √day. We don't trade this yet; see the next steps.

## Log

### 2026-10-28: volatility and the smile (`01_explore.py`)
- **LYCHEE realized vol:** 1.81–1.84% per √day from tick returns, but 1.58–1.67% from 100-tick returns. Tick returns are inflated by bid/ask bounce (lag-1 autocorrelation −0.10), so the 100-tick figure is the honest one. LYCHEE ends the days at 7,390, 7,473 and 7,406.
- **Implied vol:** solved with Black-Scholes, r = 0 and time in days. No strike ever falls outside the no-arbitrage bounds.
- **ATM IV** (constant term of a quadratic smile in log(K/S)/√T): 1.90% on day −2, 1.89% on day −1 and 2.15% on day 0.
- **Smile curvature** is about 2.9 and stable across days, with the wings higher than the middle (`02_smile.png`).
- **Residual vs a per-tick smile fit:** std 4–5 coins for the 7,200–7,750 strikes and about 1 coin for the deep wings. Autocorrelation is 0.99 at lag 1, 0.86 at lag 20 and 0.5 at lag 100. A residual predicts the next 50-tick price change with slope −0.22 to −0.47, meaning a partial close (`01_smile_residuals.csv`, `04_smile_residuals.png`).
- **Why it matters:** voucher spreads are 3 coins (6 for 6,800 and 7,000), so a 5-coin dislocation that half-closes is tradable.

### 2026-10-28: first strategy (`options.py`, `02_hedge_diagnostics.py`)
- **Design choice:** rather than fit a smile every tick, each strike tracks a slow EMA of *its own* IV. Fair value then follows LYCHEE instantly through S and treats short-lived IV moves as noise to fade. This is simpler, and it builds in the strike's typical offset from the smile.
- **Result with a tight delta hedge (band 10):** vouchers +70k, LYCHEE −94k. Without the hedge: the same +70k on vouchers, positive every day (+13.7k / +32.6k / +24.1k).
- **Why the hedge lost:** about 43k LYCHEE units crossed at a ~2-coin half-spread. The book's net delta keeps flipping sign as the market-maker's inventory turns over, so a tight hedge mostly pays the spread.
- **Decision:** don't hedge by default. Measure the risk instead (next entry).

### 2026-10-28: parameter sweep (`03_param_sweep.py`, `outputs/options/05_param_sweep_by_strike.csv`, `06_param_sweep_global.csv`)
- **Method:** unhedged, each strike depends only on LYCHEE's mid and its own book, so we backtest each strike alone and add them up. We pick one global parameter set by the worst of days −2/−1.

| Setting | d−2 | d−1 | d0 (held out) |
|---|---|---|---|
| **iv_span 1000, take 4, make 0.5, cap 50 (chosen)** | **43,940** | **37,911** | **44,732** |
| iv_span 1000, take 2, make 0.5, cap 50 | 33,976 | 46,245 | 50,094 |
| iv_span 200, take 4, make 1.5, cap 50 | 31,938 | 35,936 | 29,784 |
| iv_span 50, take 1, make 0.5, cap 50 (worst) | −49,607 | −24,154 | −30,636 |

- **Result:** a *slow* IV memory matters most. A 50-tick EMA chases noise and loses about 30–50k a day.
- **By strike:** 7,300–7,600 earn the most (5–13k a day each). Deep in-the-money 6,800 and 7,000 are mixed (−3.5k to +5.9k), and far out-of-the-money 7,900 and 8,100 are small.
- **Decision:** iv_span 1000, take 4, make 0.5, skew 1, cap 50.

### 2026-10-28: risk check (`04_risk_and_hedge.py`, `outputs/options/07_delta_and_pnl.png`)
- **Method:** record the book's net delta every tick (voucher positions × Black-Scholes delta, plus LYCHEE), using the chosen parameters.

| Version | d−2 | d−1 | d0 | mean \|delta\| | 95th pct \|delta\| |
|---|---|---|---|---|---|
| unhedged | 43,940 | 37,911 | 44,732 | 101 | 217 |
| **hedge, band 60 (chosen)** | **46,218** | **43,983** | **39,994** | **35** | **70** |
| hedge, band 120 | 52,876 | 49,811 | 38,938 | 65 | 124 |

- **Result:** unhedged, the book carries about 100 LYCHEE-equivalent units of direction, around ±12k of daily risk at LYCHEE's ~120-coin daily 1σ. A wide hedge band cuts that to a third at the same PnL. The hedge only trades when the delta is genuinely large, so it no longer pays the spread over and over.
- **Decision:** hedge with band 60. Band 120 made more in-sample, but band 60 is the better risk/return trade. Its LYCHEE leg made +3.6k, which may be luck; don't count on it.
- **Previously the TL;DR said "don't hedge"; this entry supersedes that.**

## Caveats

- **The fill model is generous**, and these strategies rely on passive fills more than any other workstream. Check them on the official backtester first.
- **Residual direction:** even hedged, the book carries up to about 70 delta (95th percentile), around ±8k of daily risk at LYCHEE's ~120-coin daily 1σ.
- **The IV EMA starts empty each day** (no memory carries over), so the first ~1,000 ticks rely on a noisy estimate. Seeding it with yesterday's per-strike IV would help.

## Open questions / next steps

1. **Smarter hedging:** hedge back to the band edge rather than to zero, or hedge passively by quoting LYCHEE at the touch with a skew. LYCHEE only prints about 58 trades a day, though.
2. **Volatility risk premium:** IV runs about 15–35% above realized. A small systematic short-vol tilt (lower fair value by a few % of vega) could add PnL, but it loses badly if LYCHEE gets jumpy on day 1. This is a good judgment call to discuss in the abstract.
3. **Seed the IVs:** start each strike's IV EMA from its day-0 closing value instead of the first tick.
4. **Smile-based fair value:** fit the smile across strikes each tick (or as a slow EMA of the coefficients) and compare it with the per-strike EMA. That could help the noisy deep in-the-money strikes.
5. **Merge:** this file is self-contained, and its take/make engine matches `standalone.py`.
