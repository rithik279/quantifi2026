# %% [markdown]
# # AMETHYST: how much of the available volume do we capture, and what blocks the rest?
# AMETHYST is worth exactly 10,000 and every trade prints at the best bid/ask, so the only limits are
# (a) how much trades and (b) whether our position is stuck at +-50, which blocks one side.
# Classic fix (IMC Prosperity): when inventory is large, also post the reducing side AT fair value
# (zero edge) to free capacity for more edge-earning fills.
# Run from repo root:  python notebooks/standalone/08_amethyst_capacity.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import data  # noqa: E402
import standalone  # noqa: E402
from datamodel import Order  # noqa: E402

A = "AMETHYST"
BASE = standalone.PARAMS[A]


class Clearing(standalone.Trader):
    """AMETHYST as in the submission, plus a zero-edge order at fair value on the reducing side once
    |position| >= clear_at (Prosperity-style inventory clearing). Records the position every tick."""

    def __init__(self, prm, clear_at=None):
        super().__init__({A: prm})
        self.clear_at = clear_at
        self.pos_path = []

    def make_orders(self, product, depth, position, fair):
        orders = super().make_orders(product, depth, position, fair)
        self.pos_path.append(position)
        if self.clear_at is not None and abs(position) >= self.clear_at:
            fv = int(round(fair))
            if position > 0:
                orders = [o for o in orders if o.quantity > 0] + [Order(product, fv, -(position + 0))] + \
                         [o for o in orders if o.quantity < 0 and o.price != fv]
            else:
                orders = [o for o in orders if o.quantity < 0] + [Order(product, fv, -position)] + \
                         [o for o in orders if o.quantity > 0 and o.price != fv]
            # stay within the limit: total sells/buys must not exceed what the limit allows
            sells = -sum(o.quantity for o in orders if o.quantity < 0)
            buys = sum(o.quantity for o in orders if o.quantity > 0)
            if position - sells < -50 or position + buys > 50:
                return super().make_orders(product, depth, position, fair)
        return orders


def run(job):
    name, prm, clear_at = job
    traders = []

    def f():
        t = Clearing(prm, clear_at); traders.append(t); return t

    res = bt.backtest(f, (-2, -1, 0), [A], record_every=0)
    pos = np.concatenate([t.pos_path for t in traders])
    return dict(variant=name, **{f"d{d.day}": d.pnl_by_product.get(A, 0.0) for d in res.days},
                units=sum(d.volume.get(A, 0) for d in res.days),
                share_time_at_limit=float(np.mean(np.abs(pos) >= 50)), mean_abs_pos=float(np.mean(np.abs(pos))))


if __name__ == "__main__":
    T = data.trades()
    tr = T[T.symbol == A]
    print(f"AMETHYST trade volume: {tr.quantity.sum()} units over 3 days ({len(tr)} trades), "
          f"all at the best bid or ask")
    jobs = [("current", BASE, None)]
    for c in (20, 30, 40, 50):
        jobs.append((f"clear at fair once |pos| >= {c}", BASE, c))
    for cap in (25, 35):
        jobs.append((f"soft cap {cap}", dict(BASE, soft_cap=cap), None))
    jobs.append(("skew 2 (lean against inventory)", dict(BASE, skew=2), None))
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(run, jobs))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["share_of_volume"] = df.units / tr.quantity.sum()
    pd.set_option("display.width", 220)
    print(df.round(3).to_string(index=False))
