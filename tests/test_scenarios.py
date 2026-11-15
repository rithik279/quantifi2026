"""Checks that the scenario edits do what they claim (src/scenarios.py).

Run:  python tests/test_scenarios.py
"""

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import backtester as bt  # noqa: E402
import scenarios as sc  # noqa: E402

P0, T0 = bt.load_prices(0), bt.load_trades(0)


def test_real_is_unchanged():
    p, t = sc.apply("real", P0, T0, 0)
    assert p.equals(P0) and t.equals(T0)


def test_shift_moves_book_and_trades():
    p, t = sc.apply("toffee_+50", P0, T0, 0)
    a, b = sc.mid_path(P0, "TOFFEE_CAKE"), sc.mid_path(p, "TOFFEE_CAKE")
    assert np.allclose(b - a, 50)
    assert np.allclose(t[t.symbol == "TOFFEE_CAKE"].price.to_numpy() - T0[T0.symbol == "TOFFEE_CAKE"].price.to_numpy(), 50)
    assert np.allclose(sc.mid_path(p, "JELLY"), sc.mid_path(P0, "JELLY"))  # others untouched


def test_mirror_twice_is_identity_and_keeps_pearl_sum():
    p, t = sc.apply("mirror", P0, T0, 0)
    s0 = sum(sc.mid_path(P0, x) for x in sc.PEARLS)
    s1 = sum(sc.mid_path(p, x) for x in sc.PEARLS)
    assert np.allclose(s1 - 50_000, -(s0 - 50_000))  # sum stays centred on 50,000
    assert (p[p["product"] == "JELLY"].bid_price_1 < p[p["product"] == "JELLY"].ask_price_1).all()
    p2, t2 = sc._sc_mirror(p.copy(), t.copy(), 0)
    assert np.allclose(sc.mid_path(p2, "JELLY"), sc.mid_path(P0, "JELLY"))


def test_mirror_flips_basket_premium():
    def prem(df):
        return sc.mid_path(df, "FRUIT_BASKET") - (2 * sc.mid_path(df, "DRAGONFRUIT") + 3 * sc.mid_path(df, "GRANADILLA") + sc.mid_path(df, "MANGOSTEEN"))
    p, _ = sc.apply("mirror", P0, T0, 0)
    assert np.allclose(prem(p), -prem(P0))


def test_widen_keeps_trades_at_the_touch():
    p, t = sc.apply("spread_+1", P0, T0, 0)
    g = p[p["product"] == "JELLY"][["timestamp", "bid_price_1", "ask_price_1"]]
    tt = t[t.symbol == "JELLY"].merge(g, on="timestamp")
    assert ((tt.price >= tt.ask_price_1) | (tt.price <= tt.bid_price_1)).all()


def test_iv_scenario_raises_voucher_prices():
    p, _ = sc.apply("iv_x1.2", P0, T0, 0)
    assert np.nanmean(sc.mid_path(p, "VOUCHER_7500") - sc.mid_path(P0, "VOUCHER_7500")) > 5


def test_bootstrap_keeps_tick_count():
    p, t = sc.apply("bootstrap_1", P0, T0, 0)
    assert len(p) == len(P0) and p.groupby("product").size().eq(10_000).all()


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for f in tests:
        f()
        print("ok ", f.__name__)
    print(f"{len(tests)} passed")
