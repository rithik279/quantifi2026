# %% [markdown]
# # Fill stress: how much PnL survives if the real engine fills us less often?
# Our backtester copies the wiki's rule: a resting order fills whenever a historical trade prints at
# our price or better. That ignores other traders ahead of us in the queue. Two pessimistic variants:
#   - passive_fill_rate r: each eligible historical trade fills us with probability r (2 seeds averaged)
#   - passive_mode "worse": only trades strictly THROUGH our price fill us (equal-price prints don't)
# Plus, for options: what if the trader assumes the wrong day (time to expiry)? The real engine never
# tells us the day, so on the website's historical replay our options trader assumes day 1 throughout.
# Run from repo root:  python notebooks/robustness/03_fill_stress.py

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

SCENARIOS = [("official rule", {})]
for r in (0.75, 0.5, 0.25):
    for s in (0, 1):
        SCENARIOS.append((f"fill rate {r:.0%}", dict(passive_fill_rate=r, seed=s)))
SCENARIOS.append(("only trades through our price", dict(passive_mode="worse")))


def jobs():
    out = [(u, {}, st, name) for u in UNITS for name, st in SCENARIOS]
    out.append(("OPTIONS_BOOK", {}, dict(no_day=True), "options assumes day 1 (no day info)"))
    return sorted(out, key=lambda j: UNITS[j[0]]["group"] != "options")


if __name__ == "__main__":
    js = jobs()
    print(f"{len(js)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, js)))
    df.to_csv(os.path.join(OUT, "03_fill_stress_runs.csv"), index=False)
    agg = df.groupby(["unit", "tag"])[["d_2", "d_1", "d0", "total"]].mean().reset_index()
    tab = agg.pivot(index="unit", columns="tag", values="total")
    order = [n for n, _ in SCENARIOS if n in tab.columns]
    order = list(dict.fromkeys(order)) + [c for c in tab.columns if c not in order]
    tab = tab[order]
    tab.loc["TOTAL"] = tab.sum()
    pd.set_option("display.width", 250)
    print((tab / 1000).round(1).to_string())
    (tab / 1000).round(2).to_csv(os.path.join(OUT, "03_fill_stress_summary_k.csv"))

    groups = {u: UNITS[u]["group"] for u in UNITS}
    g = tab.drop(index="TOTAL").groupby(lambda u: groups[u]).sum()
    cols = [c for c in order if c != "options assumes day 1 (no day info)"]
    ax = (g[cols] / 1000).T.plot(kind="bar", figsize=(10, 4))
    ax.set_ylabel("total PnL days -2..0 (k coins)"); ax.axhline(0, color="k", lw=0.5)
    ax.set_title("How much survives stricter fill assumptions (by workstream)")
    plt.xticks(rotation=20, fontsize=7); plt.tight_layout()
    plt.savefig(os.path.join(OUT, "03_fill_stress.png"), dpi=110)
