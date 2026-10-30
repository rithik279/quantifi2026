"""Checks that src/backtester.py follows the fill rules in the official wiki.

Run:  python tests/test_backtester.py   (or pytest, if installed)
"""

import os
import sys
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from backtester import DayData, run_day  # noqa: E402
from datamodel import Order  # noqa: E402


def make_day(trade_price, trade_qty=5, bids=((95, 10),), asks=((105, 10),)):
    """One tick of book for product X, and one historical trade at trade_price."""
    books = {0: {"X": (list(bids), list(asks))}}
    trades = defaultdict(lambda: defaultdict(list))
    if trade_price is not None:
        trades[0]["X"].append((trade_price, trade_qty))
    return DayData(0, [0], books, {"X": np.array([100.0])}, trades)


class OneShot:
    """Sends the given orders on the first tick only."""

    def __init__(self, orders):
        self.orders = orders

    def run(self, state):
        return {"X": self.orders}, 0, ""


def fills(orders, **kw):
    res = run_day(OneShot(orders), make_day(**kw), limits={"X": 50}, keep_fills=True)
    return res.fills, res.final_position.get("X", 0)


# Wiki examples: we bid 100.
def test_trade_below_our_bid_fills_at_our_price():
    f, pos = fills([Order("X", 100, 3)], trade_price=99)
    assert pos == 3 and f[0]["price"] == 100 and f[0]["kind"] == "passive"


def test_trade_at_our_bid_fills():
    f, pos = fills([Order("X", 100, 3)], trade_price=100)
    assert pos == 3 and f[0]["price"] == 100


def test_trade_above_our_bid_does_not_fill():
    f, pos = fills([Order("X", 100, 3)], trade_price=101)
    assert pos == 0 and not f


def test_passive_fill_capped_by_trade_quantity():
    f, pos = fills([Order("X", 100, 10)], trade_price=99, trade_qty=4)
    assert pos == 4


def test_crossing_order_fills_at_book_price_then_passive():
    # buy 15 at 106: takes 10 at the ask 105, then 5 more from a trade at 104
    f, pos = fills([Order("X", 106, 15)], trade_price=104, trade_qty=5)
    assert pos == 15
    assert f[0]["kind"] == "take" and f[0]["price"] == 105 and f[0]["qty"] == 10
    assert f[1]["kind"] == "passive" and f[1]["price"] == 106 and f[1]["qty"] == 5


def test_sell_side_mirror():
    f, pos = fills([Order("X", 100, -3)], trade_price=101)
    assert pos == -3 and f[0]["price"] == 100
    f, pos = fills([Order("X", 100, -3)], trade_price=99)
    assert pos == 0


def test_orders_over_limit_are_all_cancelled():
    res = run_day(OneShot([Order("X", 100, 30), Order("X", 101, 30)]), make_day(trade_price=99, trade_qty=100),
                  limits={"X": 50})
    assert res.final_position.get("X", 0) == 0 and res.cancelled_for_limit["X"] == 1


def test_stress_worse_mode_ignores_trades_at_our_price():
    res = run_day(OneShot([Order("X", 100, 3)]), make_day(trade_price=100), limits={"X": 50}, passive_mode="worse")
    assert res.final_position.get("X", 0) == 0
    res = run_day(OneShot([Order("X", 100, 3)]), make_day(trade_price=99), limits={"X": 50}, passive_mode="worse")
    assert res.final_position.get("X", 0) == 3


def test_stress_zero_fill_rate_blocks_passive_but_not_taking():
    res = run_day(OneShot([Order("X", 106, 15)]), make_day(trade_price=104), limits={"X": 50}, passive_fill_rate=0.0)
    assert res.final_position.get("X", 0) == 10  # takes the 10 at the ask, no passive fill


def test_pnl_marks_to_mid():
    res = run_day(OneShot([Order("X", 100, 3)]), make_day(trade_price=99), limits={"X": 50})
    # bought 3 at 100, mid 100 -> 0 PnL
    assert abs(res.total) < 1e-9


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    print(f"{len(tests)} passed")
