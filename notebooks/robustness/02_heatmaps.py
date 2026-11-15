# %% [markdown]
# # 2D sensitivity heatmaps for the parameter pairs that matter most
# One-at-a-time tests miss interactions. These grids show whether the chosen point sits inside a
# broad good region (robust) or on a ridge. Colour = total PnL over days -2..0; the chosen point is boxed.
# Each cell also shows the WORST day, since a good total can hide one bad day.
# Run from repo root:  python notebooks/robustness/02_heatmaps.py

# %%
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from units import OUT, UNITS, evaluate  # noqa: E402

PAIRS = [
    ("PINK_PEARLS", "k", [0, 0.25, 0.5, 0.75, 1.0, 1.5], "take_edge", [0.5, 1, 2, 3, 5]),
    ("PAPER_LANTERNS", "lead", [25, 50, 100, 200, 400], "slope_window", [25, 50, 100, 200, 400]),
    ("TOFFEE_CAKE", "anchor_w", [0, 0.25, 0.5, 0.75, 1.0], "take_edge", [3, 5, 8, 10, 12]),
    ("TELLURIUM", "flow_beta", [0, 0.4, 0.8, 1.2, 1.6], "soft_cap", [3, 5, 10, 20, 40]),
    ("BASKET_GROUP", "anchor", [-300, -150, 0, 150, 300], "scale", [300, 600, 1000, 1500, 2500]),
    ("OPTIONS_BOOK", "iv_span", [300, 500, 1000, 2000, 4000], "take_edge", [2, 3, 4, 6, 8]),
]


def jobs():
    out = []
    for unit, pa, va, pb, vb in PAIRS:
        for a, b in itertools.product(va, vb):
            out.append((unit, {pa: a, pb: b}, {}, f"{pa}x{pb}"))
    return sorted(out, key=lambda j: UNITS[j[0]]["group"] != "options")


if __name__ == "__main__":
    js = jobs()
    print(f"{len(js)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, js)))
    df.to_csv(os.path.join(OUT, "02_heatmap_runs.csv"), index=False)

    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))
    for ax, (unit, pa, va, pb, vb) in zip(axes.ravel(), PAIRS):
        sub = df[df.unit == unit].copy()
        sub["a"] = sub.overrides.map(lambda s: eval(s)[pa]); sub["b"] = sub.overrides.map(lambda s: eval(s)[pb])
        tot = sub.pivot(index="a", columns="b", values="total").loc[va, vb] / 1000
        worst = sub.pivot(index="a", columns="b", values="min_day").loc[va, vb] / 1000
        lim = np.nanmax(np.abs(tot.values))
        im = ax.imshow(tot.values, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
        for i in range(len(va)):
            for j in range(len(vb)):
                ax.text(j, i, f"{tot.values[i, j]:.0f}\n({worst.values[i, j]:.0f})", ha="center", va="center", fontsize=6.5)
        base = UNITS[unit]["base"]
        if base.get(pa) in va and base.get(pb) in vb:
            ax.add_patch(plt.Rectangle((vb.index(base[pb]) - 0.5, va.index(base[pa]) - 0.5), 1, 1, fill=False, lw=2.5, ec="black"))
        ax.set_xticks(range(len(vb))); ax.set_xticklabels(vb, fontsize=7); ax.set_xlabel(pb, fontsize=8)
        ax.set_yticks(range(len(va))); ax.set_yticklabels(va, fontsize=7); ax.set_ylabel(pa, fontsize=8)
        ax.set_title(f"{unit}: total k (worst day k)", fontsize=9)
        fig.colorbar(im, ax=ax, fraction=0.04)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_heatmaps.png"), dpi=100)
    print("done")
