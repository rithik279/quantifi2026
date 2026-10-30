# %% [markdown]
# # Compare two scorecards side by side (e.g. best316k vs adaptive_v1, or ours vs another branch's)
# Run from the repo root after 01_scorecard.py has produced both tags:
#   python notebooks/adaptive/04_compare.py best316k adaptive_v1

# %%
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
OUT = os.path.join(ROOT, "outputs", "adaptive")


def load(tag):
    df = pd.read_csv(os.path.join(OUT, f"scorecard_{tag}_runs.csv"))
    tot = df.groupby("scenario").pnl.sum() / 1000
    worst = df.groupby(["scenario", "day"]).pnl.sum().groupby("scenario").min() / 1000
    return tot, worst


if __name__ == "__main__":
    a, b = sys.argv[1], sys.argv[2]
    ta, wa = load(a)
    tb, wb = load(b)
    order = list(pd.read_csv(os.path.join(OUT, f"scorecard_{a}_by_group.csv"))["scenario"])
    tab = pd.DataFrame({f"{a} total": ta, f"{b} total": tb, "change": tb - ta,
                        f"{a} worst day": wa, f"{b} worst day": wb}).reindex(order)
    summary = pd.DataFrame({
        f"{a} total": [ta.loc["real"], ta.min(), ta.drop("real").mean()],
        f"{b} total": [tb.loc["real"], tb.min(), tb.drop("real").mean()],
    }, index=["real days", "worst scenario", "average over scenarios"])
    pd.set_option("display.width", 200)
    print("k coins over days -2..0\n", tab.round(1).to_string())
    print("\n", summary.round(1).to_string())
    tab.round(2).to_csv(os.path.join(OUT, f"compare_{a}_vs_{b}.csv"))

    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(order))
    ax.bar(x - 0.2, tab[f"{a} total"], 0.4, label=a)
    ax.bar(x + 0.2, tab[f"{b} total"], 0.4, label=b)
    ax.set_xticks(x); ax.set_xticklabels(order, rotation=60, ha="right", fontsize=7)
    ax.set_ylabel("PnL days -2..0 (k coins)"); ax.legend()
    ax.set_title(f"{a} vs {b} on every scenario")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f"compare_{a}_vs_{b}.png"), dpi=110)
