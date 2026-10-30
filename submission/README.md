# Submission and official-site verification

`trader.py` here is **generated**. Don't edit it; edit `src/strategies/*.py` and rebuild:

```bash
python tools/build_trader.py
```

```bash
python src/backtester.py submission/trader.py
```

The local check should print the sum of the four groups (table below).

## Checking our numbers on https://www.utefa.com/quantifi

Upload these files **in this order**. All of them import only `datamodel`, `json`, `math` and `typing`, so they can be uploaded as-is.

| # | Upload | What it tells us | Local PnL: day −2 / −1 / 0 |
|---|---|---|---|
| 1 | `src/GivenScripts/example_trader_3.py` (organizers' AMETHYST example) | **Calibration:** does our backtester match theirs? | 527 / 608 / 478 (total 1,612) |
| 2 | `src/strategies/pearls.py` | Small and simple. Mostly the PINK sum signal | 10,330 / 10,718 / 10,139 |
| 3 | `src/strategies/standalone.py` | Taking-heavy (TOFFEE_CAKE, PAPER_LANTERNS) plus market-making | 49,730 / 54,492 / 49,804 |
| 4 | `src/strategies/basket.py` | Taking-only, 4 products | 795 / 4,182 / 626 |
| 5 | `src/strategies/options.py` | The most passive-fill-heavy; also tests the day / time-to-expiry issue | 46,218 / 43,983 / 39,994 |
| 6 | `submission/trader.py` | Everything together (equals the sum of 2–5 locally) | 107,073 / 113,376 / 100,564 (total 321,012) |

For each upload, write down:
1. **PnL** per day and per product, if the site shows that breakdown, otherwise the total.
2. **How days are run:** does the site report days separately? Does position or `traderData` carry over from one day to the next, or does each day start flat?
3. **Errors, timeouts, or "orders cancelled" messages.**
4. **Run time,** if shown. Options does about 400 Black-Scholes evaluations per tick.

## How to read the differences

- **Upload 1 matches (within a few %):** our fill model is right, and the numbers in `notebooks/*/NOTES.md` can be trusted as *their* backtest numbers.
- **Upload 1 is lower:** their engine fills us less often than ours. Compare uploads 2–5 against the fill-stress table in `notebooks/robustness/NOTES.md` (fill rate 75% / 50% / 25%, and "only trades through our price"). The row that matches best becomes our planning assumption, and we re-check parameters under it. Expect market-making-heavy products (options, TELLURIUM, AMETHYST) to drop most, and taking-heavy ones (TOFFEE_CAKE, PAPER_LANTERNS, basket) the least.
- **Options way off but everything else fine:** probably time to expiry. The real engine never tells the trader the day, so on the site's replay of days −2..0 our options code assumes day 1 (5 days to expiry) throughout. The robustness notes show how much that costs locally ("options assumes day 1"). If it's the cause, it doesn't matter for the real submission, which runs on day 1.
- **Any product crashes:** the combined trader catches errors per group and keeps the others trading, then stores the error text in `traderData` under `<group>_error`. Send me the message.

## Before the final submission (Nov 1, 11:59 PM)
- [ ] Rebuild `trader.py` after the last strategy change, and re-run the local check.
- [ ] `OptionsTrader.DAY` must be 1, which is the default.
- [ ] Upload the final `trader.py` once more on the site and confirm no errors.
