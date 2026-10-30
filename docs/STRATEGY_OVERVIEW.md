# Strategy overview: what each strategy does, and how we tested it

The one-page map of our work. The detail and the full decision log are in each `notebooks/<workstream>/NOTES.md`; robustness results are in `notebooks/robustness/NOTES.md`. All PnL numbers are from our local backtester (`src/backtester.py`) on days −2 / −1 / 0, until we have the official site's numbers.

## How every strategy was built and tested (the common process)

1. **Explore:** price paths, spreads, how often each product trades, whether its moves continue or reverse (autocorrelation, variance ratio), where trades print relative to the book, and whether aggressive traders "know something" (adverse selection: does the price keep moving their way after they trade?).
2. **Find a structural reason to trade:** a relationship we can name, such as "PINK corrects the pearl sum" or "PAPER_LANTERNS trends", not just a parameter that scores well.
3. **Build the strategy** on a shared engine: estimate a fair value, take any order priced better than fair by a margin, quote at the best bid and ask otherwise, and lean quotes against inventory.
4. **Backtest** with our copy of the official fill rule: a resting order fills when a historical trade prints at our price or better. That rule is tested against the wiki's own examples (10 unit tests).
5. **Choose parameters out-of-sample:** sweep parameters, choose on days −2 and −1 (ranking by the *worse* of the two days), then check day 0, which played no part in the choice.
6. **Diagnose fills:** split PnL into taking vs passive fills and measure how the price moves after each fill. This tells us *why* a product makes or loses money.
7. **Robustness:**
   - one-at-a-time parameter sensitivity and 2D heatmaps (is the choice on a plateau or a spike?);
   - fill stress (what if the real engine fills us less often?);
   - a combined end-to-end backtest.

The key fact behind the market-making: **every historical trade prints at or beyond the best bid/ask, never inside the spread.** So under the official rule, quoting exactly at the best price catches every trade at the best price we can get.

## Standalone (`rithik/standalone`): ~52k/day

| Product | What we found | What the strategy does | How we tested it | d−2 / d−1 / d0 |
|---|---|---|---|---|
| AMETHYST | Mid only ever 9,999.5–10,000.5 | Buy below 10,000, sell above; quote at the best bid/ask | Sweep; identical across settings | 527 / 608 / 478 |
| TOFFEE_CAKE | Reverts toward ~5,000 (half-life ~70 ticks); widest spread (15); aggressors tend to be wrong | Fair value = 50/50 blend of a fast EMA and 5,000; take when price is ≥ 8 through fair | Fill split showed the profit comes from taking at deviations: sold 1,298 at avg 5,013, bought 1,248 at avg 4,992 | 24,080 / 24,774 / 21,245 |
| PAPER_LANTERNS | **Moves in straight-line segments** hidden under quote noise; the smoothed 50-tick change predicts the next 50 ticks (+0.79 / +0.82 / +0.82 by day) | Fair value = EMA + slope × 100 ticks, so we hold a position in the trend's direction | Spotted on the price chart after summary stats missed it; trend lookahead 100–300 all work (plateau) | 19,769 / 19,496 / 18,786 |
| TELLURIUM | Informed flow: after an aggressive buy, price rises ~6 within 20 ticks; 82% of trades follow the last trade's side; ~10 jumps/day of ~165 | Market-make, shifting fair value by recent signed trade flow; inventory capped at 15 | First sweep **overfit** (+15k/day in training, −23k on day 0); fixed with inventory caps; passive fills went from +0.65 to +5.2 per unit after 100 ticks; cap moved 10 → 15 to sit mid-plateau | 10,649 / 7,342 / 8,704 |
| JELLY | Random walk, no edge found | Tiny market-making (cap 3), so we still trade every product | Every setting ≈ 0 | −766 / 742 / 426 |
| PEANUT_BUTTER | Random walk, no edge found | Small market-making (cap 10) | Every setting ≈ 0 | −320 / 712 / −23 |

## Pearls (`rithik/pearls`): ~10k/day

| Product | What we found | What the strategy does | How we tested it | d−2 / d−1 / d0 |
|---|---|---|---|---|
| PINK_PEARLS | **The five pearl mids sum to 50,000 (std 5)**, and PINK is the one that closes the gap (slope −0.38 at 20 ticks, −0.98 at 200) | Fair value = mid − 0.5 × (sum − 50,000); take ≥ 1 through fair, quote at the best price | PCA confirms equal weights; sweeping k shows the signal is worth ~+7k/day (k = 0 gives ~2k/day); k from 0.5 to 1.0 all work | 10,029 / 8,930 / 9,089 |
| GOLDEN_PEARLS | Sits on 50-coin plateaus (8,000 / 7,900 / 7,800 / 7,750) | Fair value = nearest plateau | Sweep; skew moved 5 → 2 (away from a losing value at 10) | 142 / −38 / 960 |
| WHITE, BLACK, BLUE | WHITE and BLACK move opposite each other at the same tick (−0.68), but nothing predicts the next move; BLUE trends | Tiny market-making (cap 5) for breadth | Every setting ≈ 0; BLUE loses slightly | 558/2,154/496 · −160/−192/247 · −231/−327/−394 |

## Basket (`rithik/basket`): ~2k/day, low confidence

| What we found | What the strategy does | How we tested it | d−2 / d−1 / d0 |
|---|---|---|---|
| Basket ≈ 2 Dragonfruit + 3 Granadilla + 1 Mangosteen (regressions on price changes). The premium (basket − fruits) swings ±900 slowly; signals from its rolling average **flip sign day to day**, and only reversion toward a fixed level near 0 holds, resting on about one cycle | Hold baskets against the premium (−premium / 1,000 × max), hedged with the fruits (max 13 baskets, set by GRANADILLA's limit); only rebalance on changes of ≥ 4 baskets | Day-by-day signal check; hedged vs unhedged (unhedged swings by tens of thousands); sensitivity found rebalancing every 1 basket loses every day, so the threshold moved 2 → 4 | 1,589 / 5,283 / 1,036 |

## Options (`rithik/options`): ~43k/day

| What we found | What the strategy does | How we tested it | d−2 / d−1 / d0 |
|---|---|---|---|
| Time to expiry is 5 days on day 1. Each strike's implied vol is stable within a day while its price wanders about ±5 coins and partly reverts (~30% within 50 ticks). Options look expensive: implied ~1.9–2.1%/√day vs realized ~1.6% | Fair value = Black-Scholes using LYCHEE now and a slow (1,000-tick) average of the strike's own implied vol; quote at the best price, take ≥ 4 through fair; hedge LYCHEE only when net delta is more than 60 units off target | Each strike swept on its own; **tight hedging lost 94k** to LYCHEE's spread; recorded net delta every tick: band 60 cuts average exposure from 101 to 35 at the same PnL | 46,218 / 43,983 / 39,994 |

## Combined

`submission/trader.py` (generated by `tools/build_trader.py`) runs all four groups together: **112,084 / 113,468 / 101,042** locally. See `submission/README.md` for how to verify on the official site.

## Robustness in one paragraph

We moved every parameter of every strategy one notch at a time (220 backtests), ran 2D heatmaps for the six most important pairs (155 backtests), and re-ran everything with up to 75% fewer passive fills (105 backtests). Most of our PnL sits on broad plateaus. Three choices sat next to cliffs and were moved to the middle (basket rebalance threshold, GOLDEN skew, TELLURIUM inventory cap). Stricter fills cost only 8% in total, because the biggest earners take liquidity rather than wait for fills. The largest single risk is TOFFEE_CAKE's anchor: if day 1's anchor moved 50 coins away from 5,000, that product's ~23k/day would drop to about zero (not to a big loss). Details: `notebooks/robustness/NOTES.md`.
