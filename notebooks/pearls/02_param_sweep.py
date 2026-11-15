# %% [markdown]
# # Pearls: per-product parameter sweep with a walk-forward check
# Rank by the WORST of days -2/-1, report day 0 as out-of-sample. All five pearls are loaded in the
# book every run (PINK's fair value needs the other four), but only one product trades per run.
# Run from repo root:  python notebooks/pearls/02_param_sweep.py

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
import pearls  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "pearls")

MM = dict(take_edge=[1, 2, 3, 5, 100], make_edge=[0.5, 1, 2, 3], skew=[0, 2, 5], soft_cap=[5, 20])
GRIDS = {
    "WHITE_PEARLS": dict(fair=["mid"], **MM),
    "BLACK_PEARLS": dict(fair=["mid"], **MM),
    "BLUE_PEARLS": dict(fair=["mid"], **MM),
    "GOLDEN_PEARLS": dict(fair=["plateau", "mid"], step=[50], snap=[0.5, 1.0, 2.0], **MM),
    "PINK_PEARLS": dict(fair=["sum"], k=[0, 0.3, 0.5, 0.7, 1.0, 1.3], **MM),
}


def expand(grid):
    keys, seen = list(grid), set()
    for vals in itertools.product(*grid.values()):
        prm = dict(zip(keys, vals))
        if prm["fair"] != "plateau":
            prm.pop("step", None); prm.pop("snap", None)
        key = tuple(sorted(prm.items()))
        if key not in seen:
            seen.add(key)
            yield prm


def evaluate(args):
    product, prm = args
    res = bt.backtest(lambda: pearls.Trader({product: prm}), (-2, -1, 0), pearls.PEARLS, record_every=0)
    pnl = {d.day: d.pnl_by_product.get(product, 0.0) for d in res.days}
    return dict(product=product, params=prm, d_2=pnl[-2], d_1=pnl[-1], d0=pnl[0])


if __name__ == "__main__":
    jobs = [(p, prm) for p, g in GRIDS.items() for prm in expand(g)]
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(evaluate, jobs, chunksize=4))
    df = pd.DataFrame(rows)
    df["train_min"] = df[["d_2", "d_1"]].min(axis=1)
    df["train_sum"] = df[["d_2", "d_1"]].sum(axis=1)
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["params"] = df["params"].astype(str)
    df.to_csv(os.path.join(OUT, "06_param_sweep_all.csv"), index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 140)
    picks = []
    for p in GRIDS:
        d = df[df["product"] == p].sort_values(["train_min", "train_sum"], ascending=False)
        print(f"\n=== {p}: top 5 by worst training day (d0 = out-of-sample) ===")
        print(d.head(5)[["params", "d_2", "d_1", "d0", "total"]].round(0).to_string(index=False))
        picks.append(d.iloc[0])
    if "PINK_PEARLS" in GRIDS:
        k_tab = df[df["product"] == "PINK_PEARLS"].copy()
        k_tab["k"] = k_tab["params"].str.extract(r"'k': ([\d.]+)").astype(float)
        print("\nPINK: best total PnL for each k (does the sum signal matter?):")
        print(k_tab.groupby("k")[["d_2", "d_1", "d0", "total"]].max().round(0).to_string())
    pk = pd.DataFrame(picks)[["product", "params", "d_2", "d_1", "d0", "total"]]
    pk.to_csv(os.path.join(OUT, "07_param_picks.csv"), index=False)
    print("\nPicked (train on -2,-1):\n", pk.round(0).to_string(index=False))
    print("OOS day 0 total of picks:", round(pk.d0.sum()))
