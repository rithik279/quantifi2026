# Standalone notes

## 2026-10-28 — AMETHYST: fixed fair value, two-level quotes
- Hypothesis: AMETHYST's fair value is a constant 10,000.
- Test: book and trades, days -2..0. Mid never leaves 9,999.5–10,000.5. Best bid is always 9,998 or 9,999 and best ask 10,001 or 10,002 (about 50/50). All 430 trades printed at 9,998, 9,999, 10,001 or 10,002 (avg 2.5 units, ~143 per day). Nothing ever traded through 10,000.
- Variants (3-day PnL, official rule / strict `--match worse`):
  | quotes | official | strict |
  |---|---|---|
  | always 9,999 / 10,001 | 1,074.5 | 556 |
  | join best bid/ask (the given examples) | 1,612.5 | 0 |
  | always 9,998 / 10,002 | 1,094 | 0 |
  | **half at 9,998/10,002, rest at 9,999/10,001** | **1,612.5** | **556** |
- Why: trades print only at the best bid/ask. Under the official rule, a quote at exactly 9,998 fills on trades at 9,998 and earns 2. Under a strict rule only a quote that beats the trade price (9,999) fills. Splitting the size gets both. If the official engine fills our better-priced order first, the split falls back to the 9,999-only result, never worse.
- Decision: use the split in `src/strategies/standalone.py`. Also take anything offered through 10,000 (never seen so far, free if it appears on day 1). Max position was 38 of 50, so no flattening logic is needed. PnL per day is +527 / +608 / +477.5, so it's stable. This is the ceiling for AMETHYST given ~1,077 units of trade flow over 3 days.
- The other five products: see the next entry.

## 2026-10-28 — The other five: profile, then market-make around the right fair value
- Profile (days -2..0):

  | product | spread | behaviour | trades (3 days) |
  |---|---|---|---|
  | TOFFEE_CAKE | ~15 | mean-reverting: variance ratio 0.52 / 0.45 / 0.11 at 10 / 100 / 1,000 ticks, std ~22 per day | 135 |
  | PAPER_LANTERNS | 3–5 | mid bounces: lag-1 autocorrelation of changes −0.50, variance ratio 0.11 at 10 ticks | 308 |
  | TELLURIUM | ~9 | random walk (variance ratio ~1), drifts of −1,163 / +894 / +403 per day | 3,675 |
  | JELLY | ~11 | random walk | 190 |
  | PEANUT_BUTTER | ~6 | random walk, drifts of +298 / +164 / −129 | 196 |

- TELLURIUM informed flow: after a trade at the ask the mid rises +2.8 next tick and +11.7 over 50 ticks; after one at the bid it falls −2.6 / −5.6. **But we only see trades one tick later.** Measured from that tick, the effect is gone: buy- and sell-flow moves just follow each day's drift, and the correlation of the last 5–50 ticks of signed flow with the next 20 ticks is 0.02–0.04. Failed as a signal. What it does mean is that passive quotes get picked off, so TELLURIUM is quoted wide (3 from fair), small (cap 10) and leaning hard against inventory.
- Book imbalance (level 1) predicts nothing for any of the five (|corr| < 0.04 at 1 / 5 / 20 ticks, every day). Microprice is a worse predictor than mid. An EMA(0.2) of the mid beats the mid only for PAPER_LANTERNS (error vs the mid 5 ticks later: 1.52 vs 2.34).
- Grid (fair = mid or EMA with α 0.3 / 0.05 / 0.005; take ∞ / 3 / 6; make 1 / 3; skew 0 / 0.1 / 0.3; cap ¼ or full limit), scored on both fill rules and the worst day. Picked settings that were positive overall under both rules and stable against their neighbours, not the single best:

  | product | setting | days −2 / −1 / 0 | official | strict |
  |---|---|---|---|---|
  | TOFFEE_CAKE | EMA 0.3, take 3, make 1, skew 0.3, cap 12 | 2,511 / 4,750 / 3,680 | 10,941 | 10,919 |
  | PAPER_LANTERNS | EMA 0.005, no take, make 1, cap 50 | 2,645 / 2,526 / 2,697 | 7,868 | 7,077 |
  | TELLURIUM | mid, no take, make 3, skew 0.3, cap 10 | −3,414 / 5,010 / 7,750 | 9,346 | 8,714 |
  | JELLY | EMA 0.3, take 6, make 3, skew 0.1, cap 25 | 1,078 / 3,431 / −1,312 | 3,197 | 1,833 |
  | PEANUT_BUTTER | EMA 0.3, no take, make 1, skew 0.3, cap 12 | −463 / 2,822 / 198 | 2,558 | 1,728 |

- Rejected on purpose: TOFFEE_CAKE with a very slow EMA (0.005) and take 6 scored more (+17.8k), but +14k of that came from day 0 alone. JELLY with skew 0 at cap 50 gave +4.4k, but a neighbour lost −18k on day 0. Some settings fail badly: a slow EMA plus taking on a random walk fights the trend (JELLY with EMA 0.05: −45k to −163k).
- Why it works (our read): TOFFEE and PAPER have real short-horizon mean reversion around a slow-moving level, so a smoothed fair value captures the bounce. For the three random walks the only edge is the spread itself, and it only survives with small size and inventory skew. They're the weakest part of the book, and JELLY and PEANUT_BUTTER are close to noise.
