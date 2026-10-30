# Weak products: notes

Branch `rithik/weak-products`, cut from tag `best-316k` (official score 316,088). Nothing here has changed the submission. The only code change is an optional `improve` setting in `src/strategies/standalone.py` (default 0, so behaviour is unchanged). Scripts are in this folder (run from the repo root); charts and CSVs are in `outputs/weak/`.

## TL;DR

- **PEANUT_BUTTER aggressive market-making doesn't work, and the limit isn't costs.** Only ~165 units a day trade in PB, so even capturing all of them at the full 3-coin half-spread is worth at most ~500 a day. Tighter quoting already captures 92% of that volume, yet loses money: after each fill the price moves 5–9 coins against us within 100 ticks. Quoting inside the spread fills the *same* trades at a worse price.
- **Rithik's PB & J hint is right:** PEANUT_BUTTER and JELLY move together (tick correlation +0.59 to +0.61 every day, up to +0.85 over 1,000 ticks), and no other product correlates with either. JELLY ≈ 0.41 × PB + a slowly wandering gap.
- **But the pair doesn't trade.** A hedged mean-reversion trade on the gap loses on every setting and every day, because the gap wanders (350–800) more slowly than crossing both spreads costs. Its value is **hedging**: holding −0.41 PB per JELLY cuts JELLY's risk by ~30%.
- **The PB / FRUIT_BASKET resemblance is book shape, not price.** Of all 26 products, these two have the smallest spread relative to how far the price moves each tick. Their prices are unrelated (correlation ≈ 0).
- **BLUE_PEARLS momentum is real but small.** Its last 5 ticks predict the next 5 (+0.18 to +0.21 every day), but the move is ~1 coin against a 6-coin spread. Leaning BLUE's fair value with it turns −1k into roughly 0 to +2k over 3 days, with day −2 negative in every version. Not robust enough to add.
- **There is no time-of-day pattern.** The three days don't move alike on the same clock (correlation ≈ 0 for every product).
- **Left for Rithik:** GOLDEN_PEARLS and TELLURIUM.

## Log

### 2026-10-30: visual pack and scan (`01_look.py`)
- **Charts:** `01_paths.png`, `02_intraday_overlay.png`, `03_zoom_trades.png`, `04_trend_or_revert.png`.
- **Lead-lag scan:** across all 26 products, does any product's last k-tick move predict a weak product's next k ticks with the same sign on all three days? (`05_leadlag_scan.csv`)
  - **Real:** BLUE momentum at 5 ticks (+0.18 to +0.21), and pearls pushing each other at 5 ticks (BLUE up → WHITE and BLACK down next, about −0.07; consistent with the sum = 50,000 rule).
  - **Probably noise:** the 100-tick cross-product hits, like PEANUT_BUTTER "led by" LYCHEE (±0.05–0.1). A day has only ~100 independent 100-tick windows, so a correlation of ±0.1 is about one standard error, and we tested over 1,000 pairs.
- **Trade flow:** GRANADILLA's buying over the last 500 ticks predicts its next 500 (+0.18 to +0.23). That's ~20 windows a day, so it's weak evidence.
- **TELLURIUM:** flow over the last 50 ticks predicts the next 500 *negatively* (−0.11 to −0.28), the overshoot-then-revert after jumps. Trading is 5× busier in the 50 ticks after a jump (30.8 trades vs 6.1 normally), and there's no extra trading before a jump.
- **Caution about long horizons:** the variance ratio drops below 1 at 1,000–2,000 ticks for almost every product. That's mostly a finite-sample effect of measuring within a single 10,000-tick day, not evidence of mean reversion. Don't chase it.

### 2026-10-30: PEANUT_BUTTER aggressive market-making (`02_peanut_butter_mm.py`, `07_peanut_butter_mm_variants.csv`)
- **Hypothesis (Rithik):** PB looks efficient with a tight spread, so quote tight around the mid and trade as much as possible. With no transaction costs, a slim edge per trade should add up.
- **Available volume:** 194 / 153 / 148 units a day across 79 / 58 / 59 trades, all at the best bid or ask. With a 3-coin half-spread, the ceiling is about **500 a day**, even if every unit filled and the price never moved.

| Variant | Share of volume captured | Edge at fill / unit | Kept after 100 ticks / unit | PnL 3 days |
|---|---|---|---|---|
| current (best bid/ask, cap 10) | 55% | 3.20 | −8.98 | +369 |
| max size (cap 50, no lean) | 72% | 3.19 | −6.35 | −4,897 |
| tight (fair = mid, margin 0.5) | 92% | 3.02 | −5.33 | −126 |
| 1 tick inside the spread | 92% | 2.16 | −6.19 | −521 |
| 2 ticks inside the spread | 92% | 1.52 | −6.83 | −817 |

- **Why it fails:**
  1. *Volume, not cost, is the limit.* A resting order only fills when a historical trade prints at our price, and PB has ~60–80 trades a day. "No transaction costs" means we can trade as often as we like, but only by *taking*, and taking pays the spread, which is the real cost here.
  2. *Quoting inside the spread can't create volume.* Every trade already prints at the best bid or ask, so our inside quote fills on the same trades at a worse price.
  3. *Adverse moves:* after we're filled, PB keeps moving the trade's way (−5 to −9 per unit within 100 ticks), more than the 3-coin edge.
- **Decision:** keep PB at small size for breadth. No change.

### 2026-10-30: PB & J and PB / FRUIT_BASKET hints (`03_pbj_hints.py`, `08_pb_jelly_basket.png`)
- **PB vs JELLY:** price-change correlation is +0.605 / +0.589 / +0.590 tick by tick and +0.684 / +0.785 / +0.854 over 1,000 ticks. Each product's strongest correlate among all 26 is the other; everything else is under ±0.03. They move at the same time, with no lead-lag.
- **PB vs FRUIT_BASKET:** correlation ≈ 0. What looks alike is the book: these two have the smallest spread relative to their tick-by-tick moves (0.76 and 1.25, versus 3.5 for JELLY and 6 for AMETHYST). That makes taking cheap and market-making thin for both.
- **"Smooth vs bouncy":** JELLY's spread is 3.5× its typical tick move and PB's only 1.25×. JELLY's wide spread is a big cushion relative to its moves, while PB's is thin. Neither one's quotes lead the other.

### 2026-10-30: the PB & J pair (`04_pbj_pair.py`, `09_pbj_spread.png`)
- **Hedge ratio:** JELLY ≈ 0.40–0.48 × PB, stable across days (0.412 pooled from 10-tick changes).
- **The gap S = JELLY − 0.41 × PB:** mean 650 / 558 / 553 by day, std 38–85, half-life 311–2,013 ticks. It's only mildly mean-reverting (variance ratio 0.85 / 0.88 / 0.76 at 10 / 100 / 1,000 ticks), and it wanders between 350 and 800.
- **Who closes the gap:** the regression signs flip from day to day for most windows. Only the 1,000-tick average predicting the next 500 ticks kept its sign.
- **Fair value:** PB doesn't improve JELLY's (adding the gap makes JELLY's 20-tick forecast *worse*).
- **Risk:** JELLY − 0.41 × PB is 28–30% less volatile than JELLY alone, at 100 and 1,000 ticks.

### 2026-10-30: prototypes (`05_prototypes.py`, `10_prototypes.csv`)
- **PB & J pair trade:** target JELLY = −clip(gap deviation / scale) × 50, hedged with −0.41 × PB, taking liquidity. Over 18 settings it lost on every setting and every day (−24k to −382k total). The gap moves too slowly and too erratically to pay for crossing JELLY's 11-coin spread plus PB's 6.
- **BLUE momentum:** fair = mid + c × (fast EMA − slow EMA). With c > 0, BLUE goes from −0.95k to between −0.04k and +2.4k (cap 20). But day −2 is negative in every version, and the best settings vary. Not robust enough to add.

## Ideas still open

1. **PB & J hedging** in market-making: lean each product's quotes by the *combined* exposure (JELLY + 0.41 × PB) rather than its own. That's ~30% less risk, so slightly bigger size at the same risk. The expected gain is small, because market-making in both has ~zero edge after adverse moves.
2. **GRANADILLA / DRAGONFRUIT flow at 500 ticks:** weak evidence that buying predicts rises. It'd need a careful check with proper standard errors before trusting it.
3. **TELLURIUM post-jump fade** and **GOLDEN step behaviour:** Rithik is looking at these.
4. **For the abstract:** "PB & J are linked (+0.6), but the link is simultaneous, so it reduces risk rather than predicting moves" is a good depth-of-analysis point, alongside the pearls' sum rule.

### 2026-10-30: TELLURIUM spike fade / RSI (Rithik's idea) (`06_tellurium_spikes.py`, `07_tellurium_fade_backtest.py`)
- **Hypothesis (Rithik):** TELLURIUM makes sharp peaks in either direction. Measure the typical peak, fade it (sell up-spikes, buy down-spikes), exit when price is back near where the spike started, then wait for the next one. Like a VIX spike or implied-vol crush, or RSI overbought/oversold.
- **Spike study:** 28 spikes of ≥ 60 coins within 5 ticks (8 / 8 / 12 by day; 14 up, 14 down), median size 163 coins. Event list: `11_tellurium_spike_events.csv`. Chart: `11_tellurium_spike_shape.png`, every spike scaled by its size and flipped to point up.
  - **There are two kinds of spike.** About half decay smoothly back to 20–40% of the spike within ~300 ticks (the "sharp peaks"). The rest are permanent steps, or keep going to 1.5–2.5× the spike.
  - **The median spike keeps going first,** to ~1.35× by tick 200, then comes back only partway (~0.8× at 500–750 ticks).
  - **Only 39% get back to the pre-spike level within 2,000 ticks,** and 54% give back at least half. Before any reversal, the price typically runs a further 185 coins, more than the spike itself.
  - **By day it flips.** In the first 100 ticks it continued on every day (by 56% / 18% / 28% of the spike), but over 2,000 ticks day −2 kept going (−1.03) while day 0 came back (+0.48).
- **RSI** (`12_tellurium_rsi_zones.csv`): "overbought" (RSI over 50 ticks above 70) is followed by a 500-tick fall on all three days (−54 / −55 / −20). "Oversold" isn't followed by a bounce (day −2 kept falling). Entries overlap heavily, so this is weaker than it looks.
- **Backtests** (TELLURIUM only, taking liquidity, 40 units; `13_tellurium_fade_backtests.csv`):

| Strategy | Settings | Positive on all 3 days | Median total (3 days) | Best on worst day (d−2 / d−1 / d0) |
|---|---|---|---|---|
| Naive fade (wait D ticks, exit part-way back or after H) | 48 | 0 (after the bug fix below) | −18,775 | −2,364 / −3,580 / +17,800 |
| Confirmed fade (only after it starts coming back; stop at new extreme) | 36 | 0 | −8,020 | −7,553 / −7,009 / +5,936 |
| RSI overbought / oversold | 16 | 0 | −12,780 | −520 / +4,621 / −415 |
| Ride the spike (opposite idea; hold H ticks) | 32 | 0 | +1,538 | +19,588 / +9,792 / −6,694 |

- **Why it fails:** what a spike does next changes from day to day. Spikes kept going on day −2 and came back on day 0, so fading pays on some days and riding on others. Every fade that looks good earns it on day 0 and loses on days −2 and −1.
- **What does work on TELLURIUM is what we already run:** passive quotes leaning with recent trade flow, plus a small inventory cap (10.6k / 7.3k / 8.7k). It earns the spread without betting on which kind of spike it is.
- **Decision:** no change to the submission.
- **Possible follow-ups:**
  - *Risk overlay:* after a spike, cut the market maker's inventory cap for a few hundred ticks, since jumps are what hurt it.
  - *Classify spikes at the time they happen:* the trading burst after the spike, the spike's size, or the first 20 ticks' behaviour might tell the two kinds apart. With 28 events, though, any rule is easy to overfit.

### 2026-10-30: when do the spike strategies act? Bug found, and the glide idea (`08_spike_timing_example.py`, `14_spike_timing_examples.png`)
- **Question (Rithik):** are we letting the spike form fully and come back down before calling it a spike, and only then acting?
- **Answer, from a trace of real trades:** TELLURIUM's spikes are **one-tick jumps** (e.g. tick 305 on day 0: 4,717 → 4,614.5 in a single tick).
  - "Fade at once" detects the jump and enters **on that same tick**, at the post-jump price. That's the earliest possible, because the jump happens between two ticks, so there's no forming phase to sell into.
  - "Fade after D ticks" waits on purpose.
  - Only "confirmed fade" waits for the price to come back (20% of the spike), and that's by design.
  - The two-kinds-of-spike picture in the event study *is* hindsight: it's a description of what happened, not something available when we'd trade.
- **Bug found:** in the naive fade, the exit target for down-spikes was mirrored, so those trades exited one tick after entering. Fixed (`tgt = peak − f × (peak − pre)`). The re-run is *worse*: 0 of 48 settings are positive on all three days (median −18.8k). The table above is updated.
- **New observation from the trace chart:** after each jump the price **glides smoothly** toward a new level, along a curve that flattens out. That level can be back toward the start (tick 932: down to 4,204, glides back up to ~4,440; tick 1,399: up to 4,689, glides back to ~4,480) or further away (tick 305: down to 4,614, keeps gliding to ~4,480). So the useful signal isn't "fade" or "ride" the jump, but **the direction of the glide**, which shows within 20–40 ticks and then persists.
- **Glide strategy** (`GlideTrader` in `07_tellurium_fade_backtest.py`): after a jump of ≥ 60 coins within 5 ticks, wait W ticks, take 40 units in the direction the price has moved since the jump (if ≥ gmin coins), and exit when the last K-tick move stalls or reverses (or after H ticks). It takes liquidity.
  - **22 of 48 settings are positive on all three days** (median total +13.7k). The fades, RSI and ride managed 0–1 of 16–48.
  - **Best:** W = 20, gmin = 15, K = 20, flat = 0 → **+11,603 / +8,680 / +8,843**. That's the same top pick when settings are chosen on days −2/−1 only, so day 0 was effectively held out.
  - **Plateau:** W = 20 or 40 both work (10 of 16 settings positive on every day each), while W = 10 is too early (2 of 16). Exiting on a stall over K = 20 is more reliable than K = 50 (16 of 24 vs 6 of 24). gmin and H barely matter.
  - **Caveats:** chosen with all three days visible, and only ~30 jumps in total. This is TELLURIUM only and doesn't yet coexist with the market maker, which uses the same 40-unit limit.
- **Next:** combine it with the TELLURIUM market maker (for example, while a glide trade is active, push the market maker's fair value hard in the glide direction), then check it as one unit on all three days and on the official site.
