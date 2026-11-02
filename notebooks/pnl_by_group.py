"""Figure: cumulative backtest PnL by product group, one panel per day.

Run from the repo root after `python src/backtester.py submission/trader.py --save`.
Writes outputs/pnl_by_group.png.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
GROUPS = {  # fixed order and colors
    "options": "#2a78d6",
    "pearls": "#eb6834",
    "standalone": "#1baf7a",
    "basket": "#eda100",
}


def group_of(product: str) -> str:
    if product == "LYCHEE" or product.startswith("VOUCHER_"):
        return "options"
    if product.endswith("_PEARLS"):
        return "pearls"
    if product in ("FRUIT_BASKET", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"):
        return "basket"
    return "standalone"


pnl = pd.read_csv(ROOT / "data" / "processed" / "pnl_trader.csv")
products = [c for c in pnl.columns if c not in ("day", "timestamp")]
by_group = pd.DataFrame({g: pnl[[p for p in products if group_of(p) == g]].sum(axis=1) for g in GROUPS})
by_group[["day", "timestamp"]] = pnl[["day", "timestamp"]]

days = sorted(pnl.day.unique())
fig, axes = plt.subplots(1, len(days), figsize=(10, 3.4), sharey=True, facecolor=SURFACE)
for ax, d in zip(axes, days):
    part = by_group[by_group.day == d]
    x = part.timestamp / 100
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for g, color in GROUPS.items():
        ax.plot(x, part[g] / 1000, color=color, linewidth=2, label=g)
    total = part[list(GROUPS)].sum(axis=1).iloc[-1]
    ax.set_title(f"day {d}: {total / 1000:+.1f}k", color=INK, fontsize=10, loc="left")
    ax.set_xlabel("tick", color=INK_2, fontsize=8)
    ax.set_xticks([0, 5000, 10000], ["0", "5k", "10k"])
axes[0].set_ylabel("cumulative PnL (k)", color=INK_2, fontsize=9)
last = by_group[by_group.day == days[-1]].iloc[-1]
for g in GROUPS:
    axes[-1].text(10_150, last[g] / 1000, g, color=INK, fontsize=8, va="center")
axes[-1].set_xlim(0, 13_500)
axes[0].legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_2)
fig.suptitle("Backtest PnL by product group (official fill rule)", x=0.01, ha="left", color=INK, fontsize=11)
fig.tight_layout()
out = ROOT / "outputs" / "pnl_by_group.png"
fig.savefig(out, dpi=200, facecolor=SURFACE)
print(f"wrote {out.relative_to(ROOT)}")
