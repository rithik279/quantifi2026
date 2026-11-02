# CLAUDE.md

UTEFA QuantiFi 2026, Team #21. We're building one `trader.py` (an IMC Prosperity-style `Trader.run(state)`) plus an abstract of at most 5 pages. Both are due **Nov 1, 11:59 PM**.

**Read [GETTING_STARTED.md](GETTING_STARTED.md) first.** It covers the repo map, the gotchas, the workstreams and the branch workflow. The rules are in `docs/context/Official Information/`.

## Hard rules for trader code
- Match the interface in `src/GivenScripts/datamodel.py`: `run()` returns `(orders: dict[str, list[Order]], 0, traderData: str)`.
- Buy quantities are positive and sells are negative. `OrderDepth.sell_orders` volumes are negative too.
- Never let *possible* fills exceed a position limit (the official Products PDF has the limits). Size orders from the current position.
- No lookahead. At tick *t*, only use what `TradingState` gives you plus `traderData` (a JSON string). Never peek at later CSV rows.
- Voucher symbols in the data are `VOUCHER_<strike>`, not `LYCHEE_VOUCHERS_<strike>`.
- Keep imports minimal (standard library and `datamodel`; numpy and pandas haven't been confirmed for the backtester).
- Each strategy must be self-contained, because everything merges into a single submission file.

## Backtest and build
- Write strategies in `src/strategies/<ws>.py` (class with `products` and `run(state, mem)`); size orders with `OrderSet` from `strategies/common.py`.
- `python src/backtester.py src/trader.py [--days 0] [--match all|worse|none]`, then compare `--match all` with `--match worse` before trusting an edge.
- `python src/build_submission.py` writes the upload file `submission/trader.py`. Never edit that file by hand.

## Data
`data/raw/{prices,trades}_day_{-2,-1,0}.csv`, **semicolon-separated** (`pd.read_csv(path, sep=";")`). Day 1 is the scoring day, which we don't have. Write derived data to `data/processed/` (git-ignored).

## How to work here
- Stay in the current branch's workstream: `notebooks/<ws>/`, `src/strategies/<ws>.py`, `outputs/<ws>/`. Propose changes to shared code (`src/` helpers, backtester) rather than making them silently.
- **Log judgment.** After any meaningful result or decision, add an entry to `notebooks/<ws>/NOTES.md`: hypothesis, test, result, *why* it worked or failed, decision. Failed ideas get logged too. This feeds the abstract.
- Save convincing charts to `outputs/<ws>/` and link them from NOTES.md.
- Suggest a commit after each coherent step, with a message that says what changed and why. Never commit secrets. `Logic_for_Basket1.pdf` stays git-ignored.
- Treat backtest PnL with skepticism: the fill rule is generous, so prefer robust, explainable edges over tuned parameters.
