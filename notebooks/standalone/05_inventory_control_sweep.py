# %% [markdown]
# # Standalone: inventory control for the random-walk products
# The first sweep (04) overfit: TELLURIUM and JELLY picks made +15-18k/day in training and lost
# ~23k on day 0. Their PnL was inventory riding a random walk, not edge.
# Here: passive-only (no taking), join the touch, and cap inventory with soft_cap + skew.
# Selection uses the WORST of all three days, plus the spread of daily PnL, because we want
# parameters whose PnL doesn't depend on which way the price wandered.
# Run from repo root:  python notebooks/standalone/05_inventory_control_sweep.py

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
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "standalone")
BASE = dict(take_edge=[100], make_edge=[1, 3], skew=[0, 5, 15], soft_cap=[3, 10, 25, 50])
GRIDS = {
    "PAPER_LANTERNS": dict(fair=["ema"], span=[5, 20], **BASE),
    "TELLURIUM": dict(fair=["mid"], flow_beta=[0, 0.8], flow_decay=[0.9], **BASE),
    "JELLY": dict(fair=["mid"], **BASE),
    "PEANUT_BUTTER": dict(fair=["mid"], **BASE),
}


def expand(grid):
    seen = set()
    for vals in itertools.product(*grid.values()):
        prm = dict(zip(grid, vals))
        if prm.get("flow_beta", None) == 0:
            prm.pop("flow_beta"); prm.pop("flow_decay")
        k = tuple(sorted(prm.items()))
        if k not in seen:
            seen.add(k)
            yield prm


def evaluate(args):
    product, prm = args
    res = bt.backtest(lambda: standalone.Trader({product: prm}), (-2, -1, 0), [product], record_every=0)
    pnl = {d.day: d.pnl_by_product.get(product, 0.0) for d in res.days}
    return dict(product=product, params=str(prm), d_2=pnl[-2], d_1=pnl[-1], d0=pnl[0])


if __name__ == "__main__":
    jobs = [(p, prm) for p, g in GRIDS.items() for prm in expand(g)]
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs, chunksize=2)))
    days = ["d_2", "d_1", "d0"]
    df["min_day"] = df[days].min(axis=1)
    df["std_day"] = df[days].std(axis=1)
    df["total"] = df[days].sum(axis=1)
    df["train_min"] = df[["d_2", "d_1"]].min(axis=1)
    df.to_csv(os.path.join(OUT, "12_inventory_sweep_all.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    for p in GRIDS:
        d = df[df["product"] == p]
        print(f"\n=== {p}: top 6 by worst day across all three ===")
        print(d.sort_values("min_day", ascending=False).head(6)[["params"] + days + ["std_day", "total"]].round(0).to_string(index=False))
        tr = d.sort_values("train_min", ascending=False).iloc[0]
        print(f"   walk-forward pick (train -2,-1): {tr.params} -> d0 {tr.d0:.0f}")
        print("   by soft_cap (mean over other params):")
        d = d.assign(cap=d.params.str.extract(r"'soft_cap': (\d+)")[0].astype(int))
        print(d.groupby("cap")[days + ["std_day"]].mean().round(0).to_string())
