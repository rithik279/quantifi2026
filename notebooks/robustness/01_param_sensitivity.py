# %% [markdown]
# # One-at-a-time parameter sensitivity for every strategy
# For each unit, move ONE parameter at a time across a range around the chosen value (others fixed)
# and record PnL on each day. A robust choice sits on a plateau: neighbours do about as well.
# A fragile choice sits on a spike: one step away and PnL collapses.
# Run from repo root:  python notebooks/robustness/01_param_sensitivity.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from units import OUT, UNITS, evaluate  # noqa: E402

GRIDS = {
    "AMETHYST": dict(take_edge=[0.5, 1, 2, 3], make_edge=[0.5, 1, 2, 3], skew=[0, 1, 2, 5, 10]),
    "TOFFEE_CAKE": dict(span=[3, 5, 10, 20, 50], anchor=[4950, 4975, 5000, 5025, 5050], anchor_w=[0, 0.25, 0.5, 0.75, 1.0],
                        take_edge=[3, 5, 8, 10, 12], make_edge=[1, 2, 4, 6], skew=[0, 2, 5, 10]),
    "PAPER_LANTERNS": dict(span=[5, 10, 20, 50, 100], slope_window=[25, 50, 100, 200, 400], lead=[25, 50, 100, 200, 400],
                           take_edge=[0.5, 1, 2, 4], make_edge=[0.5, 1, 2], skew=[0, 1, 2, 5]),
    "TELLURIUM": dict(flow_beta=[0, 0.2, 0.4, 0.8, 1.2, 1.6], flow_decay=[0.5, 0.7, 0.8, 0.9, 0.95],
                      make_edge=[1, 2, 3, 4, 5], skew=[0, 2, 5, 10], soft_cap=[3, 5, 10, 15, 20, 40]),
    "JELLY": dict(soft_cap=[1, 3, 5, 10], make_edge=[1, 3, 5]),
    "PEANUT_BUTTER": dict(soft_cap=[3, 5, 10, 20], make_edge=[1, 2, 3, 4], skew=[0, 5, 10]),
    "PINK_PEARLS": dict(k=[0, 0.25, 0.5, 0.75, 1.0, 1.5], take_edge=[0.5, 1, 2, 3, 5], make_edge=[0.5, 1, 2],
                        skew=[0, 1, 2, 5], soft_cap=[5, 10, 15, 20]),
    "GOLDEN_PEARLS": dict(snap=[0.5, 1, 2], take_edge=[1, 2, 3], make_edge=[0.5, 1, 2], skew=[0, 2, 5, 10], soft_cap=[5, 10, 20]),
    "WHITE_PEARLS": dict(soft_cap=[1, 3, 5, 10, 20], make_edge=[1, 2, 3]),
    "BLACK_PEARLS": dict(soft_cap=[1, 3, 5, 10, 20], make_edge=[1, 2, 3]),
    "BLUE_PEARLS": dict(soft_cap=[1, 3, 5, 10, 20], make_edge=[1, 2, 3]),
    "BASKET_GROUP": dict(anchor=[-300, -150, 0, 150, 300], scale=[300, 600, 1000, 1500, 2500], min_trade=[1, 2, 4, 8]),
    "OPTIONS_BOOK": dict(iv_span=[300, 500, 1000, 2000, 4000], take_edge=[2, 3, 4, 6, 8], make_edge=[0, 0.5, 1, 1.5],
                         skew=[0, 1, 2, 4], soft_cap=[10, 25, 50], hedge_band=[30, 60, 120, 240], min_price=[1, 3, 6]),
}


def jobs():
    out = []
    for unit, grid in GRIDS.items():
        base = UNITS[unit]["base"]
        out.append((unit, {}, {}, "base"))
        for param, values in grid.items():
            for v in values:
                if base.get(param) == v:
                    continue  # identical to base
                out.append((unit, {param: v}, {}, param))
    # slowest first so the pool stays busy
    return sorted(out, key=lambda j: UNITS[j[0]]["group"] != "options")


def plateau_table(df):
    rows = []
    for unit, grid in GRIDS.items():
        base = df[(df.unit == unit) & (df.tag == "base")].iloc[0]
        for param, values in grid.items():
            bval = UNITS[unit]["base"].get(param)
            sub = df[(df.unit == unit) & (df.tag == param)].copy()
            sub["value"] = sub.overrides.map(lambda s: eval(s)[param])
            sub = pd.concat([sub, pd.DataFrame([dict(base.to_dict(), value=bval)])]).sort_values("value")
            vals = sub.value.tolist()
            i = vals.index(bval) if bval in vals else None
            neigh = sub.iloc[[j for j in (i - 1, i + 1) if i is not None and 0 <= j < len(sub)]]
            ref = abs(base.total) if base.total != 0 else 1.0
            rows.append(dict(unit=unit, param=param, base_value=bval, base_total=base.total,
                             worst_neighbour_total=neigh.total.min() if len(neigh) else float("nan"),
                             neighbour_ratio=(neigh.total.min() / base.total) if len(neigh) and base.total > 0 else float("nan"),
                             share_of_grid_within_75pct=(sub.total >= 0.75 * base.total).mean() if base.total > 0 else float("nan"),
                             best_in_grid=sub.total.max(), best_value=sub.loc[sub.total.idxmax(), "value"],
                             worst_in_grid=sub.total.min(), range_over_base=(sub.total.max() - sub.total.min()) / ref))
    return pd.DataFrame(rows)


def plot(df):
    for group in ("standalone", "pearls", "basket", "options"):
        units = [u for u in GRIDS if UNITS[u]["group"] == group]
        ncols = max(len(GRIDS[u]) for u in units)
        fig, axes = plt.subplots(len(units), ncols, figsize=(3.0 * ncols, 2.4 * len(units)), squeeze=False)
        for r, unit in enumerate(units):
            base = df[(df.unit == unit) & (df.tag == "base")].iloc[0]
            for c in range(ncols):
                ax = axes[r][c]
                if c >= len(GRIDS[unit]):
                    ax.axis("off"); continue
                param = list(GRIDS[unit])[c]
                bval = UNITS[unit]["base"].get(param)
                sub = df[(df.unit == unit) & (df.tag == param)].copy()
                sub["value"] = sub.overrides.map(lambda s: eval(s)[param])
                sub = pd.concat([sub, pd.DataFrame([dict(base.to_dict(), value=bval)])]).sort_values("value")
                x = range(len(sub))
                for col, sty in (("d_2", ":"), ("d_1", "--"), ("d0", "-.")):
                    ax.plot(x, sub[col] / 1000, sty, lw=0.7, color="grey")
                ax.plot(x, sub.total / 1000, "o-", lw=1.4, color="C0")
                bi = list(sub.value).index(bval)
                ax.plot([bi], [base.total / 1000], "o", color="red", ms=7)
                ax.set_xticks(list(x)); ax.set_xticklabels([str(v) for v in sub.value], fontsize=6)
                ax.axhline(0, color="k", lw=0.4)
                ax.set_title(f"{unit}: {param}", fontsize=7)
                ax.tick_params(labelsize=6)
        fig.suptitle(f"{group}: total PnL (k coins, blue) and each day (grey) as one parameter moves; red = chosen", fontsize=9)
        fig.tight_layout(); fig.savefig(os.path.join(OUT, f"01_sensitivity_{group}.png"), dpi=100)
        plt.close(fig)


if __name__ == "__main__":
    js = jobs()
    print(f"{len(js)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, js)))
    df.to_csv(os.path.join(OUT, "01_sensitivity_runs.csv"), index=False)
    tab = plateau_table(df)
    tab.to_csv(os.path.join(OUT, "01_sensitivity_summary.csv"), index=False)
    pd.set_option("display.width", 250)
    print(tab.round(2).to_string(index=False))
    plot(df)
