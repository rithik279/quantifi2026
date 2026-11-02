"""Figure: PINK alone pulls the pearl sum back to 50,000.

Run from the repo root: python notebooks/pearls/pink_corrector.py
Writes outputs/pearls/pink_corrector.png.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
DAYS = (-2, -1, 0)
HORIZONS = [1, 5, 10, 20, 50, 100, 200]

INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
PINK_COLOR, OTHER_COLOR = "#2a78d6", "#a3a29c"

prices = pd.concat([pd.read_csv(ROOT / f"data/raw/prices_day_{d}.csv", sep=";") for d in DAYS])
mid = prices[prices["product"].isin(PEARLS)].pivot_table(
    index=["day", "timestamp"], columns="product", values="mid_price")[PEARLS]
dev = mid.sum(axis=1) - 50_000


def slope(product: str, h: int) -> float:
    """Average over days of: h-tick change in the pearl ~ current sum deviation."""
    out = []
    for d in DAYS:
        m, dv = mid[product].xs(d), dev.xs(d)
        out.append(np.polyfit(dv[:-h], (m.shift(-h) - m)[:-h], 1)[0])
    return float(np.mean(out))


fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.6), facecolor=SURFACE,
                               gridspec_kw={"width_ratios": [1.1, 1]})
for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

# Left: how much of the sum's deviation each pearl absorbs over the next h ticks.
for p in PEARLS:
    ys = [-slope(p, h) for h in HORIZONS]  # positive = moves to close the gap
    is_pink = p == "PINK_PEARLS"
    ax1.plot(HORIZONS, ys, color=PINK_COLOR if is_pink else OTHER_COLOR,
             linewidth=2, marker="o", markersize=5 if is_pink else 3, zorder=3 if is_pink else 2)
ax1.axhline(1, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
ax1.text(HORIZONS[0], 1.04, "full correction", color=INK_2, fontsize=8, va="bottom")
ax1.text(40, 0.8, "PINK", color=INK, fontsize=9, ha="right", weight="bold")
ax1.text(HORIZONS[0], -0.12, "other four pearls", color=INK_2, fontsize=9, va="top")
ax1.set_xscale("log")
ax1.set_xticks(HORIZONS, [str(h) for h in HORIZONS])
ax1.set_ylim(-0.45, 1.15)
ax1.set_xlabel("ticks ahead", color=INK_2, fontsize=9)
ax1.set_title("Share of the sum's gap each pearl closes", color=INK, fontsize=10, loc="left")

# Right: the sum itself, one day.
d0 = dev.xs(0)
ax2.plot(d0.index / 100, d0.values, color=PINK_COLOR, linewidth=0.6)
ax2.axhline(0, color=INK_2, linewidth=1)
ax2.set_xlim(0, 2000)
ax2.set_xlabel("tick (day 0, first 2,000)", color=INK_2, fontsize=9)
ax2.set_title(f"Sum of the five pearls − 50,000  (std {dev.std():.1f})", color=INK, fontsize=10, loc="left")

fig.tight_layout()
out = ROOT / "outputs" / "pearls" / "pink_corrector.png"
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=200, facecolor=SURFACE)
print(f"wrote {out.relative_to(ROOT)}")
