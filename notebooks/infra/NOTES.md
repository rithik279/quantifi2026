# Infra notes (backtester, trader skeleton, build)

## 2026-10-28 — Local backtester and single-file build
- Goal: everyone can test a strategy locally with the official fill rule, and the four workstreams merge into one upload file without stepping on each other.
- Built: `src/backtester.py`, `src/trader.py` (routing, a `traderData` slice per strategy, crash isolation, a limit safety net), `src/strategies/common.py` (`LIMITS`, `OrderSet`), stubs for the four workstreams, and `src/build_submission.py`.
- Fill model: crossing orders fill at book prices. The rest fills against the same tick's market trades at our price if the trade printed at our price or worse (`--match all`, official). `worse` and `none` modes are there to stress-test edges. Unfilled orders are cancelled at the end of the tick. A product's orders are all cancelled if possible fills could exceed the limit.
- Checks: the three given AMETHYST examples give +1,612.5 over days -2..0 (527 / 608 / 477.5). An order over the limit is cancelled, crossing orders fill at the ask, a crashing strategy doesn't stop the others, orders for products a strategy doesn't own are dropped, oversized orders are clipped to the limit, and `traderData` round-trips every tick. The built `submission/trader.py` backtests the same as `src/trader.py`.
- Finding: the AMETHYST examples make **0** under `--match worse`/`none`. All 1,077 units filled on market trades at exactly our price (we join the best bid and ask, and trades print there). That PnL is real under the official rule, but it's the most generous part of it. (Resolved in [standalone notes](../standalone/NOTES.md): splitting quotes across two levels keeps +1,612.5 official and +556 strict.)
- Known approximation: when several of our orders could fill on the same market trade, the backtester fills them in the order we sent them. We don't know the official engine's tie-break, so when it matters, put the order you'd rather fill first.
- Open: the trader can't see the day number, so options time to expiry must assume day 1 (5 days left) in the submission. Confirmed on the official site 2026-10-28: voucher symbols are `VOUCHER_*`, and the official backtester scores 210,077 vs our 208,996 (≈ 0.5%), so the fill model matches.

## 2026-10-28 — Shared quoting helper, faster backtests
- Moved the take-then-quote logic into `common.market_make(product, depth, position, fair, {take, make, skew, cap})`. Pearls, standalone, basket and options all use it, so each strategy file only has to supply a fair value and settings. Pearls PnL is unchanged after the move (+26,937).
- Backtester: `load_day` is cached, and `run_day(..., only=[products])` / `--products` simulates only some products. A single-product grid now runs in about a second per day instead of loading everything.
- The full trader takes ~13 s for 3 days (~0.4 ms per tick), and `traderData` peaks at 631 characters.
