# %% [markdown]
# # Gated adaptivity: keep the historical value until the rolling estimate clearly moves away
# 02_adaptive_variants.py showed always-adaptive anchors cost 8-13% (TOFFEE) and ~5% (PINK) on the
# real days. A gate is a simple change detector: use the rolling estimate only once it is more than
# `gate` away from the historical value. If nothing changed, the gate never opens and nothing is lost.
# Run from the repo root:  python notebooks/adaptive/03_gated_variants.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variant_lib import OUT, evaluate  # noqa: E402

TOFFEE_SCENARIOS = ["real", "toffee_+25", "toffee_+50", "toffee_-50", "toffee_+50_midday", "toffee_drift_+100",
                    "mirror", "vol_x0.6", "vol_x1.5", "bootstrap_1", "bootstrap_2", "bootstrap_3"]
PINK_SCENARIOS = ["real", "pearls_sum_+100", "pearls_sum_+100_midday", "mirror", "vol_x0.6",
                  "bootstrap_1", "bootstrap_2", "bootstrap_3"]

UNITS = {
    "TOFFEE_CAKE": dict(
        scenarios=TOFFEE_SCENARIOS,
        variants={"fixed 5,000": {}, "always adaptive span 4000": {"anchor_span": 4000},
                  **{f"span {s} gate {g}": {"anchor_span": s, "anchor_gate": g} for s in (2000, 4000) for g in (10, 15, 20, 25)}},
    ),
    "PINK_PEARLS": dict(
        scenarios=PINK_SCENARIOS,
        variants={"fixed 50,000": {}, "always adaptive span 1000": {"sum_span": 1000},
                  **{f"span {s} gate {g}": {"sum_span": s, "sum_gate": g} for s in (1000, 2000) for g in (5, 10, 20)}},
    ),
}

if __name__ == "__main__":
    jobs = [(u, v, o, s) for u, cfg in UNITS.items() for v, o in cfg["variants"].items() for s in cfg["scenarios"]]
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs)))
    df.to_csv(os.path.join(OUT, "03_gated_variants_runs.csv"), index=False)
    pd.set_option("display.width", 250)
    for unit, cfg in UNITS.items():
        d = df[df.unit == unit]
        tab = d.pivot(index="variant", columns="scenario", values="total").loc[list(cfg["variants"]), cfg["scenarios"]] / 1000
        tab["WORST"] = tab.min(axis=1)
        tab["real_vs_fixed_%"] = 100 * (tab["real"] / tab["real"].iloc[0] - 1)
        print(f"\n=== {unit}: total PnL over 3 days, k coins ===")
        print(tab.round(1).to_string())
        tab.round(2).to_csv(os.path.join(OUT, f"03_gated_{unit}.csv"))
