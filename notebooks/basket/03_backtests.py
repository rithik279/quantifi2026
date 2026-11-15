# %% [markdown]
# # Basket: backtests of the anchored-premium strategy
# Sweep anchor/scale, hedged vs unhedged. Pick by worst of days -2/-1; day 0 is out-of-sample.
# Caveat: the anchor itself was observed on all three days, so day 0 is not fully clean.
# Run from repo root:  python notebooks/basket/03_backtests.py

# %%
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import basket  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "basket")
PRODUCTS = [basket.BASKET] + list(basket.WEIGHTS)
GRID = dict(anchor=[0, 60, 200], scale=[150, 300, 600, 1000], hedge=[False, True], min_trade=[2])


def evaluate(prm):
    res = bt.backtest(lambda: basket.Trader(prm), (-2, -1, 0), PRODUCTS, record_every=0)
    return dict(key=str(prm), **{f"d{d.day}": d.total for d in res.days},
                basket_only=sum(d.pnl_by_product.get(basket.BASKET, 0) for d in res.days))


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(evaluate, combos))
    df = pd.DataFrame(rows).rename(columns={"d-2": "d_2", "d-1": "d_1"}).set_index("key")
    df["train_min"] = df[["d_2", "d_1"]].min(axis=1)
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df = df.sort_values("train_min", ascending=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 100)
    print(df.round(0).to_string())
    df.to_csv(os.path.join(OUT, "04_backtest_sweep.csv"))

    # PnL curve for the best hedged and best unhedged
    fig, ax = plt.subplots(figsize=(12, 4))
    for hedged in (False, True):
        key = df[df.index.str.contains(f"'hedge': {hedged}")].index[0]
        res = bt.backtest(lambda: basket.Trader(eval(key)), (-2, -1, 0), PRODUCTS, record_every=100)
        off = 0.0
        for i, d in enumerate(res.days):
            c = d.pnl_curve["TOTAL"] + off
            ax.plot(c.index / 100 + i * 10_000, c.values, color="C1" if hedged else "C0",
                    label=("hedged " if hedged else "unhedged ") + key if i == 0 else None, lw=0.8)
            off = c.iloc[-1]
    ax.legend(fontsize=7); ax.set_title("Basket strategy cumulative PnL (days -2, -1, 0)")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "05_pnl_curves.png"), dpi=110)
