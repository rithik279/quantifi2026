"""Local backtester that copies the official QuantiFi fill rule.

Usage (from the repo root):
    python src/backtester.py src/trader.py                  # days -2, -1, 0
    python src/backtester.py src/trader.py --days 0 --match worse
    python src/backtester.py submission/trader.py --save    # per-tick PnL CSV

How a tick works (same as IMC Prosperity and the QuantiFi wiki):
1. `run(state)` sees the book at tick t, our position, our fills from the
   previous tick (`own_trades`) and the market trades of the previous tick.
2. Limit check: if position + all buys (or all sells) for a product could
   exceed the limit, every order for that product is cancelled.
3. Orders that cross the book fill at the book's prices, up to its volume.
4. What's left fills passively against the market trades at tick t
   (from trades_day_*.csv) at *our* price, if the trade price is equal to or
   worse than ours for the other side. Trade volume is used only once.
5. Unfilled orders are cancelled. PnL = cash + position * mid.

--match controls step 4: "all" (official: equal or worse), "worse" (strictly
worse only, more conservative), "none" (book-crossing fills only). If an edge
only survives under "all", treat it with suspicion.

Each day runs on its own: a fresh Trader, flat positions and empty traderData,
like the single scoring day.
"""

import argparse
import contextlib
import functools
import importlib.util
import io
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src" / "GivenScripts"), str(ROOT / "src")]

from datamodel import Listing, Observation, OrderDepth, Trade, TradingState  # noqa: E402
from strategies.common import LIMITS  # noqa: E402

DATA = ROOT / "data" / "raw"


@functools.lru_cache(maxsize=None)
def load_day(day: int):
    """Return ({ts: {product: (bids, asks, mid)}}, {ts: [Trade]}) for one day."""
    prices = pd.read_csv(DATA / f"prices_day_{day}.csv", sep=";")
    books: dict = defaultdict(dict)
    for row in prices.itertuples(index=False):
        bids, asks = {}, {}
        for n in (1, 2, 3):
            bp, bv = getattr(row, f"bid_price_{n}"), getattr(row, f"bid_volume_{n}")
            ap, av = getattr(row, f"ask_price_{n}"), getattr(row, f"ask_volume_{n}")
            if not math.isnan(bp):
                bids[int(bp)] = int(bv)
            if not math.isnan(ap):
                asks[int(ap)] = -int(av)
        books[row.timestamp][row.product] = (bids, asks, row.mid_price)

    trades = pd.read_csv(DATA / f"trades_day_{day}.csv", sep=";")
    market: dict = defaultdict(list)
    for row in trades.itertuples(index=False):
        price = int(row.price) if float(row.price).is_integer() else float(row.price)
        market[row.timestamp].append(
            Trade(row.symbol, price, int(row.quantity), None, None, row.timestamp)
        )
    return books, market


def load_trader(path: Path):
    spec = importlib.util.spec_from_file_location("trader_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Trader


def check_orders(result) -> None:
    """Fail loudly on malformed orders instead of silently doing something odd."""
    if not isinstance(result, dict):
        raise TypeError(f"run() must return a dict of orders, got {type(result)}")
    for symbol, orders in result.items():
        if symbol not in LIMITS:
            raise ValueError(f"unknown symbol {symbol!r}")
        for o in orders:
            if o.symbol != symbol:
                raise ValueError(f"order {o} listed under {symbol!r}")
            if not isinstance(o.price, int) or not isinstance(o.quantity, int):
                raise TypeError(f"price and quantity must be ints: {o}")


def run_day(trader_cls, day: int, match: str, verbose: bool, only=None):
    """Backtest one day. `only` limits the market to some products (faster)."""
    books, market = load_day(day)
    timestamps = sorted(books)
    products = sorted({p for ts in timestamps for p in books[ts]})
    if only:
        products = [p for p in products if p in only]
    listings = {p: Listing(p, p, "COINS") for p in products}

    trader = trader_cls()
    trader_data = ""
    position = defaultdict(int)
    cash = defaultdict(float)
    last_mid = {}
    own_prev: dict = {}
    market_prev: dict = {}
    stats = defaultdict(lambda: defaultdict(int))  # product -> counters
    pnl_rows = []

    for ts in timestamps:
        depths = {}
        for p in products:
            if p not in books[ts]:
                continue
            bids, asks, mid = books[ts][p]
            depths[p] = OrderDepth(dict(bids), dict(asks))
            if not math.isnan(mid):
                last_mid[p] = mid

        state = TradingState(
            traderData=trader_data,
            timestamp=ts,
            listings=listings,
            order_depths=depths,
            own_trades=own_prev,
            market_trades=market_prev,
            position={p: q for p, q in position.items() if q != 0},
            observations=Observation({}, {}),
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(sys.stdout if verbose else out):
            result, _conversions, trader_data = trader.run(state)
        check_orders(result)
        if not isinstance(trader_data, str):
            raise TypeError("traderData must be a string")

        # Market trades at this tick, with remaining volume we can take.
        tick_trades = defaultdict(list)
        for t in market.get(ts, []):
            tick_trades[t.symbol].append([t, t.quantity])

        own_now = defaultdict(list)
        for symbol, orders in result.items():
            if symbol not in depths:
                continue
            limit = LIMITS[symbol]
            buys = sum(o.quantity for o in orders if o.quantity > 0)
            sells = sum(o.quantity for o in orders if o.quantity < 0)
            if position[symbol] + buys > limit or position[symbol] + sells < -limit:
                stats[symbol]["limit_cancels"] += 1
                continue

            book_bids = dict(books[ts][symbol][0])
            book_asks = {p: -v for p, v in books[ts][symbol][1].items()}
            for o in orders:
                remaining = abs(o.quantity)
                side = 1 if o.quantity > 0 else -1

                # 1) Cross the visible book at its prices.
                levels = sorted(book_asks) if side > 0 else sorted(book_bids, reverse=True)
                for lvl in levels:
                    if remaining == 0 or (side > 0 and lvl > o.price) or (side < 0 and lvl < o.price):
                        break
                    book = book_asks if side > 0 else book_bids
                    q = min(remaining, book[lvl])
                    if q > 0:
                        book[lvl] -= q
                        remaining -= q
                        position[symbol] += side * q
                        cash[symbol] -= side * q * lvl
                        own_now[symbol].append(Trade(symbol, lvl, q,
                            "SUBMISSION" if side > 0 else None,
                            None if side > 0 else "SUBMISSION", ts))

                # 2) Passive fill against this tick's market trades at our price.
                if match == "none":
                    continue
                for entry in tick_trades[symbol]:
                    if remaining == 0:
                        break
                    t, avail = entry
                    if avail == 0:
                        continue
                    if side > 0:
                        ok = t.price < o.price or (match == "all" and t.price == o.price)
                    else:
                        ok = t.price > o.price or (match == "all" and t.price == o.price)
                    if not ok:
                        continue
                    q = min(remaining, avail)
                    entry[1] -= q
                    remaining -= q
                    position[symbol] += side * q
                    cash[symbol] -= side * q * o.price
                    stats[symbol]["passive_fills"] += q
                    own_now[symbol].append(Trade(symbol, o.price, q,
                        "SUBMISSION" if side > 0 else None,
                        None if side > 0 else "SUBMISSION", ts))

        for symbol, fills in own_now.items():
            stats[symbol]["volume"] += sum(f.quantity for f in fills)
        for p in products:
            stats[p]["max_abs_pos"] = max(stats[p]["max_abs_pos"], abs(position[p]))

        own_prev = dict(own_now)
        market_prev = {
            s: [Trade(t.symbol, t.price, left, None, None, ts) for t, left in lst if left > 0]
            for s, lst in tick_trades.items()
        }
        pnl_rows.append({"day": day, "timestamp": ts, **{
            p: cash[p] + position[p] * last_mid.get(p, 0.0) for p in products
        }})

    final = pnl_rows[-1]
    summary = pd.DataFrame({
        "pnl": {p: final[p] for p in products},
        "volume": {p: stats[p]["volume"] for p in products},
        "passive": {p: stats[p]["passive_fills"] for p in products},
        "max_pos": {p: stats[p]["max_abs_pos"] for p in products},
        "limit_cancels": {p: stats[p]["limit_cancels"] for p in products},
    })
    return summary, pd.DataFrame(pnl_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("trader", type=Path, help="path to a file defining class Trader")
    ap.add_argument("--days", type=int, nargs="+", default=[-2, -1, 0])
    ap.add_argument("--match", choices=["all", "worse", "none"], default="all")
    ap.add_argument("--save", action="store_true",
                    help="write per-tick PnL to data/processed/pnl_<trader>.csv")
    ap.add_argument("--verbose", action="store_true", help="show the trader's prints")
    ap.add_argument("--products", nargs="+", help="only simulate these products (faster)")
    args = ap.parse_args()

    trader_cls = load_trader(args.trader.resolve())
    per_day, curves = {}, []
    for day in args.days:
        summary, curve = run_day(trader_cls, day, args.match, args.verbose, args.products)
        per_day[day] = summary
        curves.append(curve)
        print(f"day {day:>2}: total PnL {summary.pnl.sum():>12,.1f}")

    pnl = pd.DataFrame({f"day {d}": s.pnl for d, s in per_day.items()})
    pnl["total"] = pnl.sum(axis=1)
    extra = sum(s[["volume", "passive", "limit_cancels"]] for s in per_day.values())
    extra["max_pos"] = pd.concat([s.max_pos for s in per_day.values()], axis=1).max(axis=1)
    table = pd.concat([pnl, extra], axis=1)
    table = table[(table.volume > 0) | (table.limit_cancels > 0)]
    pd.set_option("display.width", 160)
    print(f"\nmatch={args.match}  (products with no activity hidden)")
    print(table.round(1).to_string() if len(table) else "(no trades)")
    print(f"\nTOTAL {pnl['total'].sum():,.1f}")
    if table.limit_cancels.sum() > 0:
        print("WARNING: some ticks had all orders cancelled for exceeding a position limit.")

    if args.save:
        out = ROOT / "data" / "processed" / f"pnl_{args.trader.stem}.csv"
        pd.concat(curves).to_csv(out, index=False)
        print(f"saved per-tick PnL to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
