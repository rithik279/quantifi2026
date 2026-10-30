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
| 2 | `src/strategies/pearls.py` | Small and simple. Mostly the PINK sum signal | 10,338 / 10,528 / 10,397 |
| 3 | `src/strategies/standalone.py` | Taking-heavy (TOFFEE_CAKE, PAPER_LANTERNS) plus market-making (TELLURIUM, AMETHYST) | 53,939 / 53,674 / 49,615 |
| 4 | `src/strategies/basket.py` | Taking-only, 4 products | 1,589 / 5,283 / 1,036 |
| 5 | `src/strategies/options.py` | Mostly taking; also tests the day / time-to-expiry issue | 46,218 / 43,983 / 39,994 |
| 6 | `submission/trader.py` | Everything together (equals the sum of 2–5 locally) | 112,084 / 113,468 / 101,042 (total 326,594) |

Upload from the `rithik/robustness` branch: it has the latest parameters and the combined file.

**Candidate (2026-10-30, branch `rithik/weak-products`, not tagged):** best-357k plus a GOLDEN_PEARLS slide overlay. `submission/trader.py` there scores **120,906 / 127,082 / 112,982 = 360,970** locally (only GOLDEN changed, 1,064 → 5,043). Not yet checked on the official site.

**Current best: tag `best-357k` (branch `rithik/weak-products`, 2026-10-30):** the same files plus a TELLURIUM glide overlay. `submission/trader.py` there scores **120,906 / 125,083 / 111,002 = 356,991** locally (versus 326,594 for `best-316k`; only TELLURIUM changed, 26,694 → 57,092). `src/strategies/standalone.py` alone: 62,762 / 65,289 / 59,574. **Official site: ~357k**, matching local.

**Results so far (2026-10-30):** #6 `submission/trader.py` scored **316,088** on the official site, versus 326,594 locally (3.2% lower). Our backtester is well calibrated. Uploads #2–#5 would show which group accounts for the gap.

For each upload, write down:
1. **PnL** per day and per product, if the site shows that breakdown, otherwise the total.
2. **How days are run:** does the site report days separately? Does position or `traderData` carry over from one day to the next, or does each day start flat?
3. **Errors, timeouts, or "orders cancelled" messages.**
4. **Run time,** if shown. Options does about 400 Black-Scholes evaluations per tick.

## How to read the differences

- **Upload 1 matches (within a few %):** our fill model is right, and the numbers in `notebooks/*/NOTES.md` can be trusted as *their* backtest numbers.
- **Upload 1 is lower:** their engine fills us less often than ours. Compare uploads 2–5 against the fill-stress table in `notebooks/robustness/NOTES.md` (fill rate 75% / 50% / 25%, and "only trades through our price"). The row that matches best becomes our planning assumption, and we re-check parameters under it. Locally only TELLURIUM and AMETHYST are sensitive to this; the taking-based products (options, TOFFEE_CAKE, PAPER_LANTERNS, PINK, basket) barely move.
- **Options way off but everything else fine:** it's *not* the day issue. Assuming day 1 throughout costs only 0.1k locally. Check for errors or timeouts instead (options is the heaviest per tick), and send me the numbers.
- **Any product crashes:** the combined trader catches errors per group and keeps the others trading, then stores the error text in `traderData` under `<group>_error`. Send me the message.

## Before the final submission (Nov 1, 11:59 PM)
- [ ] Rebuild `trader.py` after the last strategy change, and re-run the local check.
- [ ] `OptionsTrader.DAY` must be 1, which is the default.
- [ ] Upload the final `trader.py` once more on the site and confirm no errors.
