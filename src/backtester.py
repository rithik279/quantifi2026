"""Local QuantiFi backtester, mirroring the official fill rules from the wiki.

Each tick:
  1. Trader.run(state) is called with the order book at t, plus our own fills and
     the market trades from the previous tick.
  2. If a product's orders could take |position| past its limit, all of that
     product's orders are cancelled (Prosperity behaviour).
  3. Orders that cross the book fill at the book's prices, level by level.
  4. Any remainder fills passively against the historical trades at t when the
     trade price is equal or better for us (buy fills if trade price <= our
     price), at OUR price, up to the trade's quantity.
  5. Unfilled orders are cancelled; nothing rests into the next tick.

Days are run independently (fresh Trader, flat position), like Prosperity.
PnL is cash plus position marked at the mid price.

Assumptions that are NOT confirmed by the organizers:
  - Market trades consumed by our passive fills are removed from state.market_trades.
  - Days do not carry position over.
  - Remaining quantity after crossing does not rest into the next tick.

Usage:
    python src/backtester.py src/strategies/pearls.py
    python src/backtester.py src/GivenScripts/example_trader_3.py --days 0 --products AMETHYST
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "GivenScripts"))

from datamodel import Listing, Observation, Order, OrderDepth, Trade, TradingState  # noqa: E402

DATA_DIR = os.path.join(ROOT, "data", "raw")

POSITION_LIMITS: Dict[str, int] = {
    "AMETHYST": 50, "TOFFEE_CAKE": 50, "PAPER_LANTERNS": 50, "TELLURIUM": 40,
    "JELLY": 50, "PEANUT_BUTTER": 50,
    "DRAGONFRUIT": 40, "GRANADILLA": 40, "MANGOSTEEN": 40, "FRUIT_BASKET": 40,
    "LYCHEE": 200,
    "WHITE_PEARLS": 20, "BLACK_PEARLS": 20, "GOLDEN_PEARLS": 20, "PINK_PEARLS": 20, "BLUE_PEARLS": 20,
}
for _k in (6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100):
    POSITION_LIMITS[f"VOUCHER_{_k}"] = 50


# =========================
# Data loading
# =========================
def load_prices(day: int) -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, f"prices_day_{day}.csv"), sep=";")


def load_trades(day: int) -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, f"trades_day_{day}.csv"), sep=";")


@dataclass
class DayData:
    day: int
    timestamps: List[int]
    # books[ts][product] = (bids [(price, vol)], asks [(price, vol)]) with positive volumes
    books: Dict[int, Dict[str, tuple]]
    mids: Dict[str, np.ndarray]  # product -> mid per timestamp index
    trades: Dict[int, Dict[str, List[tuple]]]  # ts -> symbol -> [(price, qty)]


def load_day(day: int, products: Optional[Iterable[str]] = None) -> DayData:
    prices = load_prices(day)
    trades = load_trades(day)
    if products is not None:
        products = set(products)
        prices = prices[prices["product"].isin(products)]
        trades = trades[trades["symbol"].isin(products)]

    timestamps = sorted(prices["timestamp"].unique().tolist())
    books: Dict[int, Dict[str, tuple]] = defaultdict(dict)
    cols = prices[["timestamp", "product"] + [f"{s}_{k}_{i}" for i in (1, 2, 3) for s in ("bid", "ask") for k in ("price", "volume")]]
    for row in cols.itertuples(index=False):
        ts, prod = row[0], row[1]
        vals = row[2:]
        bids, asks = [], []
        for i in range(3):
            bp, bv, ap, av = vals[4 * i: 4 * i + 4]
            if bp == bp:  # not NaN
                bids.append((int(bp), int(bv)))
            if ap == ap:
                asks.append((int(ap), int(av)))
        books[ts][prod] = (bids, asks)

    mids = {}
    for prod, g in prices.groupby("product"):
        mids[prod] = g.sort_values("timestamp")["mid_price"].to_numpy()

    tr: Dict[int, Dict[str, List[tuple]]] = defaultdict(lambda: defaultdict(list))
    for row in trades[["timestamp", "symbol", "price", "quantity"]].itertuples(index=False):
        tr[row[0]][row[1]].append((int(row[2]), int(row[3])))

    return DayData(day, timestamps, dict(books), mids, tr)


# =========================
# Results
# =========================
@dataclass
class DayResult:
    day: int
    pnl_by_product: Dict[str, float]
    final_position: Dict[str, int]
    n_fills: Dict[str, int]
    volume: Dict[str, int]
    cancelled_for_limit: Dict[str, int]
    pnl_curve: pd.DataFrame  # index timestamp, columns product (+ TOTAL)
    fills: List[dict] = field(default_factory=list)

    @property
    def total(self) -> float:
        return float(sum(self.pnl_by_product.values()))


@dataclass
class BacktestResult:
    days: List[DayResult]

    def summary(self) -> pd.DataFrame:
        rows = {}
        for d in self.days:
            rows[d.day] = d.pnl_by_product
        df = pd.DataFrame(rows).fillna(0.0)
        df["TOTAL"] = df.sum(axis=1)
        df.loc["TOTAL"] = df.sum(axis=0)
        return df

    @property
    def total(self) -> float:
        return float(sum(d.total for d in self.days))


# =========================
# Engine
# =========================
def _load_trader(path: str):
    spec = importlib.util.spec_from_file_location(f"trader_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Trader


def run_day(trader, data: DayData, record_every: int = 100, keep_fills: bool = False,
            limits: Dict[str, int] = POSITION_LIMITS) -> DayResult:
    position: Dict[str, int] = defaultdict(int)
    cash: Dict[str, float] = defaultdict(float)
    n_fills: Dict[str, int] = defaultdict(int)
    volume: Dict[str, int] = defaultdict(int)
    cancelled: Dict[str, int] = defaultdict(int)
    trader_data = ""
    own_prev: Dict[str, List[Trade]] = {}
    market_prev: Dict[str, List[Trade]] = {}
    products = sorted(data.mids.keys())
    listings = {p: Listing(p, p, "COINS") for p in products}
    curve_rows, curve_idx, fills = [], [], []

    for i, ts in enumerate(data.timestamps):
        book = data.books[ts]
        order_depths = {}
        for p, (bids, asks) in book.items():
            od = OrderDepth()
            od.buy_orders = {px: v for px, v in bids}
            od.sell_orders = {px: -v for px, v in asks}
            order_depths[p] = od

        state = TradingState(
            traderData=trader_data, timestamp=ts, listings=listings, order_depths=order_depths,
            own_trades=own_prev, market_trades=market_prev,
            position={p: q for p, q in position.items() if q != 0},
            observations=Observation({}, {}),
        )
        out = trader.run(state)
        if isinstance(out, tuple):
            result = out[0]
            trader_data = out[2] if len(out) > 2 and out[2] is not None else ""
        else:
            result = out
        result = result or {}

        own_now: Dict[str, List[Trade]] = defaultdict(list)
        # mutable copies of the book and of this tick's market trades
        live_book = {p: ([list(x) for x in b], [list(x) for x in a]) for p, (b, a) in book.items()}
        tick_trades = {s: [list(x) for x in lst] for s, lst in data.trades.get(ts, {}).items()}

        for prod, orders in result.items():
            if not orders or prod not in live_book:
                continue
            lim = limits.get(prod, 0)
            pos = position[prod]
            buy_total = sum(o.quantity for o in orders if o.quantity > 0)
            sell_total = -sum(o.quantity for o in orders if o.quantity < 0)
            if pos + buy_total > lim or pos - sell_total < -lim:
                cancelled[prod] += 1
                continue

            bids, asks = live_book[prod]
            for o in orders:
                qty = o.quantity
                price = int(o.price)
                if qty == 0:
                    continue
                remaining = abs(qty)
                side = 1 if qty > 0 else -1
                # 1) cross the visible book at book prices
                levels = asks if side == 1 else bids
                for lvl in levels:
                    if remaining == 0:
                        break
                    lpx, lvol = lvl
                    if lvol <= 0:
                        continue
                    if (side == 1 and lpx <= price) or (side == -1 and lpx >= price):
                        f = min(remaining, lvol)
                        lvl[1] -= f
                        remaining -= f
                        position[prod] += side * f
                        cash[prod] -= side * f * lpx
                        n_fills[prod] += 1
                        volume[prod] += f
                        own_now[prod].append(Trade(prod, lpx, f, "SUBMISSION" if side == 1 else "", "SUBMISSION" if side == -1 else "", ts))
                        if keep_fills:
                            fills.append(dict(ts=ts, product=prod, side=side, price=lpx, qty=f, kind="take"))
                # 2) passive fill against historical trades at an equal-or-better price, at our price
                if remaining > 0:
                    for t in tick_trades.get(prod, []):
                        if remaining == 0:
                            break
                        tpx, tq = t
                        if tq <= 0:
                            continue
                        if (side == 1 and tpx <= price) or (side == -1 and tpx >= price):
                            f = min(remaining, tq)
                            t[1] -= f
                            remaining -= f
                            position[prod] += side * f
                            cash[prod] -= side * f * price
                            n_fills[prod] += 1
                            volume[prod] += f
                            own_now[prod].append(Trade(prod, price, f, "SUBMISSION" if side == 1 else "", "SUBMISSION" if side == -1 else "", ts))
                            if keep_fills:
                                fills.append(dict(ts=ts, product=prod, side=side, price=price, qty=f, kind="passive"))

        own_prev = dict(own_now)
        market_prev = {s: [Trade(s, px, q, None, None, ts) for px, q in lst if q > 0] for s, lst in tick_trades.items()}
        market_prev = {s: v for s, v in market_prev.items() if v}

        if record_every and (i % record_every == 0 or i == len(data.timestamps) - 1):
            row = {p: cash[p] + position.get(p, 0) * data.mids[p][i] for p in list(cash)}
            curve_rows.append(row)
            curve_idx.append(ts)

    last = len(data.timestamps) - 1
    pnl = {p: cash[p] + position.get(p, 0) * data.mids[p][last] for p in list(cash)}
    curve = pd.DataFrame(curve_rows, index=curve_idx).ffill().fillna(0.0)
    if not curve.empty:
        curve["TOTAL"] = curve.sum(axis=1)
    return DayResult(data.day, pnl, dict(position), dict(n_fills), dict(volume), dict(cancelled), curve, fills)


_DAY_CACHE: Dict[tuple, DayData] = {}


def get_day(day: int, products: Optional[Iterable[str]] = None) -> DayData:
    key = (day, tuple(sorted(products)) if products else None)
    if key not in _DAY_CACHE:
        _DAY_CACHE[key] = load_day(day, products)
    return _DAY_CACHE[key]


def backtest(trader_factory, days: Iterable[int] = (-2, -1, 0), products: Optional[Iterable[str]] = None,
             record_every: int = 100, keep_fills: bool = False) -> BacktestResult:
    """trader_factory: a Trader class or a zero-arg callable returning a fresh trader.

    If the trader has a `set_day(day)` method it is called before the day starts. The real engine
    never tells the trader the day; this hook only exists so backtests of day-dependent logic
    (e.g. option time-to-expiry) are right. Submissions should default to the scoring day (1).
    """
    res = []
    for d in days:
        data = get_day(d, products)
        trader = trader_factory()
        if hasattr(trader, "set_day"):
            trader.set_day(d)
        res.append(run_day(trader, data, record_every=record_every, keep_fills=keep_fills))
    return BacktestResult(res)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trader", help="path to a .py file defining class Trader")
    ap.add_argument("--days", type=int, nargs="+", default=[-2, -1, 0])
    ap.add_argument("--products", nargs="+", default=None, help="restrict the book to these products (faster)")
    args = ap.parse_args()

    Trader = _load_trader(os.path.abspath(args.trader))
    t0 = time.time()
    res = backtest(Trader, args.days, args.products)
    pd.set_option("display.width", 200)
    print(res.summary().round(0).astype(int).to_string())
    for d in res.days:
        if d.cancelled_for_limit:
            print(f"day {d.day}: orders cancelled for position limit -> {d.cancelled_for_limit}")
    print(f"\nTOTAL PnL: {res.total:,.0f}   ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
