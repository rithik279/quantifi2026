"""Figure: the voucher vol smile by day, against LYCHEE's realized vol.

Run from the repo root: python notebooks/options/smile.py
Writes outputs/options/smile.png. Time to expiry: 8 days at the start of day -2.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[2]
DAYS = (-2, -1, 0)
STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = [f"VOUCHER_{k}" for k in STRIKES]

INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
DAY_COLORS = {-2: "#2a78d6", -1: "#eb6834", 0: "#1baf7a"}

prices = pd.concat([pd.read_csv(ROOT / f"data/raw/prices_day_{d}.csv", sep=";") for d in DAYS])
mid = prices[prices["product"].isin(VOUCHERS + ["LYCHEE"])].pivot_table(
    index=["day", "timestamp"], columns="product", values="mid_price")
day = mid.index.get_level_values(0).values
T = (8 - (day + 2)) - mid.index.get_level_values(1).values / 1e6
S = mid.LYCHEE.values


def call(S, K, T, sig):
    sd = sig * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * sd ** 2) / sd
    return S * norm.cdf(d1) - K * norm.cdf(d1 - sd)


iv = {}
for K, v in zip(STRIKES, VOUCHERS):
    C = mid[v].values
    lo, hi = np.full_like(C, 1e-4), np.full_like(C, 0.2)
    for _ in range(60):
        m = (lo + hi) / 2
        above = call(S, K, T, m) > C
        hi, lo = np.where(above, m, hi), np.where(above, lo, m)
    sig = (lo + hi) / 2
    sig[C <= np.maximum(S - K, 0) + 0.01] = np.nan
    iv[K] = sig
iv = pd.DataFrame(iv, index=mid.index)
realized = mid.LYCHEE.groupby(level=0).apply(lambda s: np.log(s).diff().std() * np.sqrt(10_000)).mean()

fig, ax = plt.subplots(figsize=(6.4, 3.6), facecolor=SURFACE)
ax.set_facecolor(SURFACE)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(GRID)
ax.tick_params(colors=INK_2, labelsize=9)
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)

means = iv.groupby(level=0).mean()
for d in DAYS:
    ys = means.loc[d].values * 100
    ax.plot(STRIKES, ys, color=DAY_COLORS[d], linewidth=2, marker="o", markersize=5, label=f"day {d}")
    ax.text(STRIKES[-1] + 40, ys[-1], f"day {d}", color=INK, fontsize=9, va="center")
ax.axhline(realized * 100, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
ax.text(STRIKES[0], realized * 100 + 0.02, f"LYCHEE realized vol ({realized * 100:.2f})", color=INK_2, fontsize=8, va="bottom")
ax.axvline(mid.LYCHEE.mean(), color=GRID, linewidth=1)
ax.text(mid.LYCHEE.mean() + 20, 2.5, "LYCHEE ≈ 7,436", color=INK_2, fontsize=8, va="top")
ax.set_xlim(STRIKES[0] - 60, STRIKES[-1] + 260)
ax.set_xlabel("strike", color=INK_2, fontsize=9)
ax.set_ylabel("implied vol, % per √day", color=INK_2, fontsize=9)
ax.set_title("Voucher implied vol by strike (daily average)", color=INK, fontsize=10, loc="left")
ax.legend(frameon=False, fontsize=8, loc="upper right", labelcolor=INK_2)
ax.set_ylim(1.7, None)

fig.tight_layout()
out = ROOT / "outputs" / "options" / "smile.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=200, facecolor=SURFACE)
print(f"wrote {out.relative_to(ROOT)}")
