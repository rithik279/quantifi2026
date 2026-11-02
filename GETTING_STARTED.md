# Getting Started

This is our shared home base: a quick map of what's here, what we've learned so far, and how we can split the work so everyone moves fast in parallel without losing sight of each other's progress. It's written for you and for whatever coding agent you use, so either can get up to speed in a few minutes. Nothing here is fixed. If you see a better way to organize things, change it.

**Team #21:** Selena Zhang, Michael Xu, Jeffery Hu, Rithik Singh
**Deadline:** Nov 1, 11:59 PM. Submit one `trader.py` plus an abstract of at most 5 pages.

## 1. What we're building

We're building a single Python file with a `Trader` class whose `run(state)` method trades all products on the QuantiFi backtester. The format is the same as IMC Prosperity. We're judged on:

1. **Breadth:** trade every product, with different strategies.
2. **Depth:** how well each strategy fits its product.
3. **Communication:** the abstract.
4. **PnL:** profit on day 1, which isn't in our data.

## 2. Where everything is

| Path | What's there | Read it when |
|---|---|---|
| `notebooks/PROGRESS.md` | Team status: what's done, PnL so far, open decisions, next steps | Every time you sit down |
| `docs/context/Official Information/` | Official wiki: rules, product list, `TradingState`, how fills work | First. It's short, and it settles most rules questions |
| `docs/context/GeneratedDocs/ClaudeInitialExplaination.pdf` | First-pass analysis of every product, a good map of the work | Before picking a workstream |
| `docs/context/GeneratedDocs/UTEFA QuantiFi 2026_Initialbrainstorm.pdf` | Team brainstorm and principles | Once |
| `data/raw/` | `prices_day_{-2,-1,0}.csv` and `trades_day_{-2,-1,0}.csv`, **semicolon-separated** | Exploration |
| `src/GivenScripts/` | `datamodel.py`, which the backtester provides, and 3 example AMETHYST traders | Writing strategy code |
| `notebooks/` | Exploration notebooks, one folder per workstream | Your daily work |
| `src/` | Strategy code that will be merged into the final trader | When a strategy is ready |
| `data/processed/` | Your own derived data (git-ignored, regenerate it locally) | As needed |
| `outputs/` | Charts and tables for the abstract | When you find something worth showing |

Load the data like this:

```python
import pandas as pd
prices = pd.read_csv("data/raw/prices_day_0.csv", sep=";")
trades = pd.read_csv("data/raw/trades_day_0.csv", sep=";")
```

## 3. Gotchas we've found so far

Add to this list as you hit new ones, so nobody loses time on the same thing twice.


- **Voucher names:** the wiki says `LYCHEE_VOUCHERS_7300`, but the data says `VOUCHER_7300`. Use the data's names, and confirm them on the backtester.
- **Position limits are hard:** if your orders *could* push you past a limit, they get cancelled. Size your orders using your current position.
- **Quantity signs:** buy quantities are positive, sell quantities are negative. `sell_orders` in `OrderDepth` also stores negative volumes.
- **Fills are generous:** your passive order fills if a real historical trade happened at your price or a worse one for the other side. Backtest PnL will overstate live PnL.
- **No lookahead:** `run()` only sees the current tick. Anything you remember has to go through `traderData`, a JSON string.
- **One file at the end:** the submission is a single `trader.py`, so keep each strategy self-contained so it's easy to merge.
- **Equal-price fills carry the easy PnL:** the AMETHYST examples make +1,612 over 3 days under the official rule, and **0** under `--match worse`. Every fill came from a market trade at exactly our price. The official scorer uses the generous rule, so this counts, but compare both modes before trusting an edge.
- **The trader can't see the day:** `TradingState` has `timestamp` but no day number. Anything that depends on it (option time to expiry) has to assume scoring day 1 (5 days to expiry at its start), and needs a setting to backtest days -2..0.

## 4. Workstreams

Splitting by product group lets us work in parallel, but the groups aren't really independent. For example, LYCHEE hedging touches the options strategy, the pearls and basket groups both depend on relationships between products, and the same market-making core can serve several groups. The starting ideas below come from a first pass over the data, so treat them as hypotheses to test, not conclusions. Put your name next to what you're picking up, and feel free to pair up on a group.

| Workstream | Products | Starting idea (to verify) | Owner |
|---|---|---|---|
| `standalone` | AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM, JELLY, PEANUT_BUTTER | Market-make around a fair value estimated for each product. TELLURIUM's counterparties seem to know which way it's about to move. | |
| `basket` | FRUIT_BASKET, DRAGONFRUIT, GRANADILLA, MANGOSTEEN | Basket ≈ 2D + 3G + 1M. Trade large gaps between the basket and the value of its parts. | |
| `options` | LYCHEE, VOUCHER_* (10 strikes) | Black-Scholes implied vol, smile relative value, delta-hedge with LYCHEE | |
| `pearls` | WHITE, BLACK, GOLDEN, PINK, BLUE_PEARLS | The five prices sum to ~50,000. PINK corrects the sum, and GOLDEN moves in steps. | |

## 5. Backtesting and building the submission

The shared pieces live in `src/`:

| File | What it does |
|---|---|
| `src/strategies/common.py` | `LIMITS`, `best_bid`/`best_ask`/`mid_price`, `OrderSet` (clips orders so possible fills never break a limit) and `market_make` (take what's mispriced, then quote inside the spread around a fair value you supply) |
| `src/strategies/<ws>.py` | One class per workstream (`products`, `run(state, mem)`). The stubs return no orders, so fill yours in |
| `src/trader.py` | Routes each product to its strategy, gives each strategy its own slice of `traderData` (`mem`), isolates crashes, clips to limits |
| `src/backtester.py` | Local copy of the official fill rule. Prints PnL per product and day |
| `src/build_submission.py` | Pastes everything into `submission/trader.py`. Fails on non-stdlib imports or name clashes between files |

```bash
python src/backtester.py src/trader.py                 # all three days
python src/backtester.py src/trader.py --days 0 --match worse
python src/build_submission.py                         # then upload submission/trader.py
python src/backtester.py submission/trader.py          # must match src/trader.py
```

`--match` sets how resting orders fill against market trades: `all` (official: equal or worse price), `worse` (strictly worse only) or `none` (only orders that cross the book). `--products A B` simulates only those products, which is much faster when you're tuning one. `--save` writes per-tick PnL to `data/processed/` for plots. `--verbose` shows your prints. Crashes always show. Each day runs on its own, from a flat position, like the scoring day. About 2 s per day with no strategies.

Inside your strategy, size orders with `OrderSet` and keep anything you need between ticks in `mem` (small and JSON-serialisable). Keep module-level names unique (prefix helpers, e.g. `pearls_fair_value`), because all files end up in one.

## 6. Starting work on a branch

```bash
git checkout main
git pull
git checkout -b <yourname>/<workstream>
```

For example, `selena/pearls` or `michael/options`.

Put your work here:

- `notebooks/<workstream>/`: exploration, such as `notebooks/pearls/01_sum_constraint.ipynb`
- `src/strategies/<workstream>.py`: the strategy code, once it works
- `outputs/<workstream>/`: charts you'd put in the abstract

Commit often, and push your branch so others can see it:

```bash
git push -u origin <yourname>/<workstream>
```

When a strategy is ready, open a pull request into `main` and ask someone else to review it. A second set of eyes catches lookahead bugs and limit mistakes fast. Mostly keeping changes inside your own workstream's folders keeps merges painless. For shared pieces like the backtester, common helpers or the final `trader.py`, a quick heads-up in the group chat avoids two people building the same thing.

## 7. Working together

- **Share findings early.** A rough chart or a one-line "PINK seems to lead the sum" in the chat is worth more than a polished result two days later. Someone else's group may depend on it.
- **Build shared tools once.** A local backtester that copies the official fill rule, plus common order-book helpers, will help every workstream. If you start on one, say so, and put it in `src/` for everyone.
- **Sync regularly.** A short check-in every day or two to compare results, rebalance work and decide what goes into the final file.

### Document your judgment, not just your code

Most of the code will be written with agents, so the most valuable thing each of us adds is **judgment**: what we chose to try, why, and what we concluded. Capture that as you go. It's what turns into a strong abstract, since Depth and Communication are half the first-round score. It's also what lets us defend our choices in front of the judges at National Bank.

Keep a running log at `notebooks/<workstream>/NOTES.md`. Add a short entry whenever you make a decision or get a result:

```markdown
## 2026-10-29 — PINK as the sum corrector
- Hypothesis: PINK moves to restore sum(pearls) ≈ 50,000.
- Test: regressed PINK's 50-tick change on (sum − 50,000), days -2..0.
- Result: slope ≈ −0.65, consistent across all 3 days. Backtest PnL +X.
- Why it works (our read): ...
- Decision: use 50,000 − sum(others) as PINK's fair value. Next: check GOLDEN steps.
```

- **Explain why, especially when something fails.** "Mean reversion on JELLY lost money because the spread is tighter than the reversion" is a finding. A failed idea we understand is worth almost as much as a working one, both for the abstract and for not repeating it.
- **Commit diligently.** Commit small and often, with messages that say what changed *and* why ("Widen TELLURIUM quotes: informed flow was picking us off"). Push your branch at the end of every session, so nothing lives only on one laptop and teammates can see where you are.
- **Save the evidence.** When a chart or table convinces you of something, save it to `outputs/<workstream>/` and link it from your notes. Those become the abstract's figures.

## 8. Notes for coding agents

- Read `docs/context/Official Information/` and section 3 above before writing any trader code.
- Strategy code must only import what the backtester allows: the standard library, `datamodel`, and possibly `numpy` and `pandas` (confirm this with the organizers).
- Never use future rows of the CSVs when making a decision at tick *t*.
- Prefer the current branch's workstream folders. If a change to shared code (`src/` helpers, the backtester) would help, propose it to your user rather than making it silently.
- When you find something notable, or a decision gets made, add an entry to `notebooks/<workstream>/NOTES.md` (hypothesis, test, result, why, decision) so teammates and their agents can build on it.
