# %% [markdown]
# # PAPER_LANTERNS: trend-following fair value
# fair = EMA(span) + slope(slope_window) * lead, then the usual take/make engine.
# A large `lead` makes fair sit beyond the touch in the trend's direction, so the engine takes
# and holds a position with the trend; a small lead is just a better-centred market maker.
# Pick by worst of days -2/-1; day 0 is out-of-sample.
# Run from repo root:  python notebooks/standalone/07_lanterns_trend_sweep.py

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
P = "PAPER_LANTERNS"
GRID = dict(fair=["trend"], span=[20, 50], slope_window=[100, 300], lead=[0, 25, 100, 300],
            take_edge=[1, 3, 100], make_edge=[1], skew=[0, 2])


def evaluate(prm):
    res = bt.backtest(lambda: standalone.Trader({P: prm}), (-2, -1, 0), [P], record_every=0)
    return dict(params=str(prm), **{f"d{d.day}": d.pnl_by_product.get(P, 0.0) for d in res.days})


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, combos, chunksize=2))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["train_min"] = df[["d_2", "d_1"]].min(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df.to_csv(os.path.join(OUT, "15_lanterns_trend_sweep.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 150)
    print(df.sort_values("train_min", ascending=False).head(10).round(0).to_string(index=False))
    df["lead"] = df.params.str.extract(r"'lead': (\d+)")[0].astype(int)
    print("\nBest result for each lead (does extrapolating the trend help?):")
    print(df.groupby("lead")[["d_2", "d_1", "d0", "total"]].max().round(0).to_string())
