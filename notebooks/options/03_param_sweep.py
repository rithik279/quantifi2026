# %% [markdown]
# # Options: parameter sweep (unhedged), run per strike for speed
# Unhedged, each voucher only depends on LYCHEE's mid and its own book, so each strike is
# backtested alone and results are summed. We pick ONE global parameter set (not per strike) by
# the worst of days -2/-1, and report day 0 as out-of-sample.
# Run from repo root:  python notebooks/options/03_param_sweep.py

# %%
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "options")
GRID = dict(iv_span=[50, 200, 1000], take_edge=[1, 2, 4], make_edge=[0.5, 1.5], soft_cap=[25, 50], skew=[1])


class OneVoucher(options.Trader):
    """Trades a single voucher; LYCHEE is only used for pricing."""

    def __init__(self, product, params):
        super().__init__(dict(params, hedge=False))
        self.only = product

    def run(self, state):
        result, conv, td = super().run(state)
        return {k: v for k, v in result.items() if k == self.only}, conv, td


def evaluate(args):
    product, prm = args
    res = bt.backtest(lambda: OneVoucher(product, prm), (-2, -1, 0), [options.UNDERLYING, product], record_every=0)
    return dict(product=product, key=str(prm), **{f"d{d.day}": d.pnl_by_product.get(product, 0.0) for d in res.days})


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    jobs = [(p, c) for c in combos for p in options.VOUCHERS]
    print(f"{len(jobs)} backtests ({len(combos)} parameter sets x {len(options.VOUCHERS)} strikes)")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(evaluate, jobs, chunksize=2))
    df = pd.DataFrame(rows).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df.to_csv(os.path.join(OUT, "05_param_sweep_by_strike.csv"), index=False)

    agg = df.groupby("key")[["d_2", "d_1", "d0"]].sum()
    agg["train_min"] = agg[["d_2", "d_1"]].min(axis=1)
    agg["total"] = agg[["d_2", "d_1", "d0"]].sum(axis=1)
    agg = agg.sort_values("train_min", ascending=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    print("\nTop 10 global parameter sets by worst training day (d0 = OOS):\n", agg.head(10).round(0).to_string())
    print("\nBottom 3:\n", agg.tail(3).round(0).to_string())
    best = agg.index[0]
    print(f"\nBest set {best} by strike:\n", df[df.key == best].set_index("product")[["d_2", "d_1", "d0"]].round(0).to_string())
    agg.to_csv(os.path.join(OUT, "06_param_sweep_global.csv"))
