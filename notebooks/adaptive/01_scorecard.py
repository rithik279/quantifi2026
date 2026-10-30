# %% [markdown]
# # Scorecard: run a trader on every "what might the judges change?" scenario
# Scenarios are edited copies of the real days (src/scenarios.py). Also runs the real days back to
# back with position and traderData carried over ("continuous"), in case the official engine does that.
#
# Run from the repo root:
#   python notebooks/adaptive/01_scorecard.py                                  # scores submission/trader.py
#   python notebooks/adaptive/01_scorecard.py path/to/other_trader.py --tag mine
# Outputs: outputs/adaptive/scorecard_<tag>_runs.csv, _by_group.csv, _vs_real.png

# %%
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import backtester as bt  # noqa: E402
import scenarios as sc  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "adaptive")
os.makedirs(OUT, exist_ok=True)

GROUP = {p: "standalone" for p in sc.STANDALONE}
GROUP.update({p: "pearls" for p in sc.PEARLS})
GROUP.update({p: "basket" for p in sc.BASKET_GROUP})
GROUP.update({p: "options" for p in sc.OPTION_PRODUCTS})


def run(args):
    trader_path, scenario = args
    Trader = bt._load_trader(trader_path)
    if scenario == "continuous":
        res = bt.backtest(Trader, record_every=0, continuous=True)
    else:
        res = bt.backtest(Trader, record_every=0, scenario=scenario)
    rows = []
    for d in res.days:
        for p, v in d.pnl_by_product.items():
            rows.append(dict(scenario=scenario, day=d.day, product=p, pnl=v))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trader", nargs="?", default=os.path.join(ROOT, "submission", "trader.py"))
    ap.add_argument("--tag", default="best316k")
    ap.add_argument("--scenarios", nargs="*", default=None)
    a = ap.parse_args()
    names = a.scenarios or (list(sc.SCENARIOS) + ["continuous"])
    jobs = [(os.path.abspath(a.trader), s) for s in names]
    print(f"scoring {a.trader} on {len(jobs)} scenarios")
    with ProcessPoolExecutor() as ex:
        rows = [r for rs in ex.map(run, jobs) for r in rs]
    df = pd.DataFrame(rows)
    df["group"] = df["product"].map(GROUP)
    df.to_csv(os.path.join(OUT, f"scorecard_{a.tag}_runs.csv"), index=False)

    by_group = df.pivot_table(index="scenario", columns="group", values="pnl", aggfunc="sum").reindex(names)
    by_group["TOTAL"] = by_group.sum(axis=1)
    by_day = df.pivot_table(index="scenario", columns="day", values="pnl", aggfunc="sum").reindex(names)
    by_group["worst_day"] = by_day.min(axis=1)
    real = by_group.loc["real"]
    by_group["vs_real_%"] = 100 * (by_group["TOTAL"] / real["TOTAL"] - 1)
    by_group.round(0).to_csv(os.path.join(OUT, f"scorecard_{a.tag}_by_group.csv"))
    pd.set_option("display.width", 250)
    print((by_group / [1000] * 1).round(1).assign(**{"vs_real_%": by_group["vs_real_%"].round(1)}).to_string())

    # product-level change vs the real data, for the products that carry PnL
    key = ["TOFFEE_CAKE", "PAPER_LANTERNS", "TELLURIUM", "AMETHYST", "PINK_PEARLS", "GOLDEN_PEARLS"]
    prod = df.pivot_table(index="scenario", columns="product", values="pnl", aggfunc="sum").reindex(names).fillna(0)
    view = pd.concat([prod[key], by_group[["basket", "options"]]], axis=1)
    delta = (view - view.loc["real"]) / 1000
    print("\nChange vs real data (k coins, 3 days), key products:\n", delta.round(1).to_string())
    delta.round(2).to_csv(os.path.join(OUT, f"scorecard_{a.tag}_delta_by_product.csv"))

    fig, ax = plt.subplots(figsize=(10, 0.42 * len(names) + 1.5))
    lim = np.nanmax(np.abs(delta.values))
    im = ax.imshow(delta.values, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(delta.shape[0]):
        for j in range(delta.shape[1]):
            ax.text(j, i, f"{delta.values[i, j]:+.0f}", ha="center", va="center", fontsize=7)
    ax.set_xticks(range(delta.shape[1])); ax.set_xticklabels(delta.columns, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(delta.shape[0])); ax.set_yticklabels(delta.index, fontsize=8)
    ax.set_title(f"{a.tag}: PnL change vs real data, k coins over 3 days (red = hurt)", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, f"scorecard_{a.tag}_vs_real.png"), dpi=100)


if __name__ == "__main__":
    main()
