# %% [markdown]
# # Adaptive vs fixed: test each adaptive version on the scenarios that broke the fixed one
# Three hard-coded facts carried almost all of best-316k's scenario losses:
#   TOFFEE_CAKE anchor 5,000      -> adaptive anchor (slow EMA starting at 5,000), anchor_span
#   pearl sum target 50,000       -> adaptive target (slow EMA of the sum starting at 50,000), sum_span
#   options take threshold 4 coins -> threshold scaled by each voucher's recent wobble size
# Each unit is run alone (only the products it needs) on: the real days, the scenarios that hurt it,
# and assumption-free scenarios (mirror, block reshuffles) to check adaptivity doesn't cost elsewhere.
# Choice rule: best WORST case across scenarios, with at most a small cost on the real data.
# Run from the repo root:  python notebooks/adaptive/02_adaptive_variants.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variant_lib import OUT, evaluate  # noqa: E402

UNITS = {
    "TOFFEE_CAKE": dict(
        scenarios=["real", "toffee_+25", "toffee_+50", "toffee_-50", "toffee_+50_midday", "toffee_drift_+100",
                   "mirror", "vol_x0.6", "vol_x1.5", "bootstrap_1", "bootstrap_2", "bootstrap_3"],
        variants={"fixed 5,000": {}, **{f"adaptive span {s}": {"anchor_span": s} for s in (500, 1000, 2000, 4000, 8000)}},
    ),
    "PINK_PEARLS": dict(
        scenarios=["real", "pearls_sum_+100", "pearls_sum_+100_midday", "mirror", "vol_x0.6",
                   "bootstrap_1", "bootstrap_2", "bootstrap_3"],
        variants={"fixed 50,000": {}, **{f"adaptive span {s}": {"sum_span": s} for s in (200, 500, 1000, 2000, 5000)}},
    ),
    "OPTIONS_BOOK": dict(
        scenarios=["real", "iv_x0.8", "iv_x1.2", "lychee_vol_x1.5"],
        variants={"fixed 4 coins": {},
                  **{f"scaled k={k} min={m}": {"take_mode": "scaled", "take_k": k, "take_min": m}
                     for k, m in ((0.6, 2.0), (0.8, 2.0), (1.0, 2.0), (0.8, 3.0))}},
    ),
}


if __name__ == "__main__":
    jobs = [(u, v, o, s) for u, cfg in UNITS.items() for v, o in cfg["variants"].items() for s in cfg["scenarios"]]
    jobs.sort(key=lambda j: j[0] != "OPTIONS_BOOK")  # slowest first
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs)))
    df.to_csv(os.path.join(OUT, "02_adaptive_variants_runs.csv"), index=False)
    pd.set_option("display.width", 250)
    for unit, cfg in UNITS.items():
        d = df[df.unit == unit]
        tab = d.pivot(index="variant", columns="scenario", values="total").loc[list(cfg["variants"]), cfg["scenarios"]] / 1000
        tab["WORST"] = tab.min(axis=1)
        tab["real_vs_fixed_%"] = 100 * (tab["real"] / tab["real"].iloc[0] - 1)
        print(f"\n=== {unit}: total PnL over 3 days, k coins ===")
        print(tab.round(1).to_string())
        tab.round(2).to_csv(os.path.join(OUT, f"02_adaptive_{unit}.csv"))
