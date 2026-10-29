# %% [markdown]
# # Pearls: figures for the abstract
# 1. PINK PnL by k (how much the sum-constraint signal is worth), from the sweep CSV.
# 2. Final-parameter PnL curves per pearl.
# Run from repo root after 02_param_sweep.py:  python notebooks/pearls/03_figures.py

# %%
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import pearls  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "pearls")

df = pd.read_csv(os.path.join(OUT, "06_param_sweep_all.csv"))
pink = df[df["product"] == "PINK_PEARLS"].copy()
pink["k"] = pink["params"].str.extract(r"'k': ([\d.]+)")[0].astype(float)
best = pink.groupby("k")[["d_2", "d_1", "d0"]].max()
ax = best.plot(kind="bar", figsize=(7, 3.5))
ax.set_ylabel("PnL (best params for each k)")
ax.set_title("PINK_PEARLS: fair = mid - k x (sum of pearls - 50,000)")
ax.legend(["day -2", "day -1", "day 0 (out-of-sample)"], fontsize=7)
plt.tight_layout(); plt.savefig(os.path.join(OUT, "08_pink_pnl_by_k.png"), dpi=110)

res = bt.backtest(pearls.Trader, (-2, -1, 0), pearls.PEARLS, record_every=100)
print(res.summary().round(0).to_string())
fig, ax = plt.subplots(figsize=(12, 4))
offset = {}
for i, d in enumerate(res.days):
    for p in pearls.PEARLS:
        if p not in d.pnl_curve:
            continue
        c = d.pnl_curve[p] + offset.get(p, 0.0)
        ax.plot(c.index / 100 + i * 10_000, c.values, lw=0.8, color=f"C{pearls.PEARLS.index(p)}", label=p if i == 0 else None)
        offset[p] = c.iloc[-1]
ax.legend(fontsize=7); ax.set_title("Pearls strategy cumulative PnL by product (days -2, -1, 0)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "09_pnl_curves.png"), dpi=110)
