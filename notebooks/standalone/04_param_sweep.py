# %% [markdown]
# # Standalone: per-product parameter sweep with a walk-forward check
# Products don't interact in this strategy, so each one is swept alone (fast).
# Selection rule: rank by the WORST of days -2 and -1 (robustness), then report day 0 as the
# out-of-sample check. We never pick on day 0.
# Run from repo root:  python notebooks/standalone/04_param_sweep.py

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

GRIDS = {
    "AMETHYST": dict(fair=["fixed"], value=[10_000], take_edge=[0.5, 1, 2], make_edge=[0.5, 1, 2], skew=[0, 2, 5]),
    "TOFFEE_CAKE": dict(fair=["ema"], span=[10, 50], anchor=[5_000], anchor_w=[0, 0.5, 1.0],
                        take_edge=[2, 5, 8], make_edge=[2, 5], skew=[0, 5, 15]),
    "PAPER_LANTERNS": dict(fair=["ema", "mid"], span=[5, 20, 100], take_edge=[1, 2, 3, 100], make_edge=[0.5, 1, 2], skew=[0, 2, 5]),
    "TELLURIUM": dict(fair=["mid"], flow_beta=[0, 0.3, 0.8], flow_decay=[0.7, 0.9], take_edge=[4, 8, 100],
                      make_edge=[1, 3, 5], skew=[0, 5, 15]),
    "JELLY": dict(fair=["mid", "ema"], span=[5], flow_beta=[0, 0.5], flow_decay=[0.95], take_edge=[2, 4, 100],
                  make_edge=[1, 3, 5], skew=[0, 4, 10]),
    "PEANUT_BUTTER": dict(fair=["mid", "ema"], span=[5], flow_beta=[0, 0.5], flow_decay=[0.95], take_edge=[2, 4, 100],
                          make_edge=[1, 3, 5], skew=[0, 4, 10]),
}


def expand(grid):
    keys = list(grid)
    seen = set()
    for vals in itertools.product(*grid.values()):
        prm = dict(zip(keys, vals))
        if prm.get("fair") != "ema":
            prm.pop("span", None)
        if prm.get("flow_beta", None) == 0:
            prm.pop("flow_beta"); prm.pop("flow_decay", None)
        if prm.get("anchor_w", None) == 0:
            prm.pop("anchor"); prm.pop("anchor_w")
        key = tuple(sorted(prm.items()))
        if key not in seen:
            seen.add(key)
            yield prm


def evaluate(args):
    product, prm = args
    res = bt.backtest(lambda: standalone.Trader({product: prm}), (-2, -1, 0), [product], record_every=0)
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
    df.to_csv(os.path.join(OUT, "10_param_sweep_all.csv"), index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 140)
    picks = []
    for p in GRIDS:
        d = df[df["product"] == p].sort_values(["train_min", "train_sum"], ascending=False)
        print(f"\n=== {p}: top 5 by worst training day (d0 = out-of-sample) ===")
        print(d.head(5)[["params", "d_2", "d_1", "d0", "total"]].round(0).to_string(index=False))
        print(f"   default params -> ", df[(df["product"] == p) & (df["params"] == str({k: v for k, v in standalone.PARAMS[p].items()}))][["d_2", "d_1", "d0"]].round(0).to_dict("records"))
        picks.append(d.iloc[0])
    pk = pd.DataFrame(picks)[["product", "params", "d_2", "d_1", "d0", "total"]]
    pk.to_csv(os.path.join(OUT, "11_param_picks.csv"), index=False)
    print("\nPicked (train on -2,-1):\n", pk.round(0).to_string(index=False))
    print("OOS day 0 total of picks:", round(pk.d0.sum()))
