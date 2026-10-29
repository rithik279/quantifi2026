# %% [markdown]
# # Options: is the LYCHEE hedge helping?
# Compare hedged vs unhedged, and measure how much the hedge trades and what it costs.
# Run from repo root:  python notebooks/options/02_hedge_diagnostics.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402

PRODUCTS = [options.UNDERLYING] + list(options.VOUCHERS)
VARIANTS = {
    "hedged_band10": dict(hedge=True, hedge_band=10),
    "hedged_band40": dict(hedge=True, hedge_band=40),
    "unhedged": dict(hedge=False),
}


def run(name):
    res = bt.backtest(lambda: options.Trader(VARIANTS[name]), (-2, -1, 0), PRODUCTS, keep_fills=True)
    out = {}
    for d in res.days:
        f = pd.DataFrame(d.fills)
        lf = f[f["product"] == options.UNDERLYING] if len(f) else f
        out[d.day] = dict(total=d.total, lychee=d.pnl_by_product.get("LYCHEE", 0.0),
                          vouchers=d.total - d.pnl_by_product.get("LYCHEE", 0.0),
                          lychee_units=int(lf["qty"].sum()) if len(lf) else 0,
                          voucher_units=int(f[f["product"] != options.UNDERLYING]["qty"].sum()) if len(f) else 0,
                          max_abs_lychee_pos=None)
    return name, out


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        results = dict(ex.map(run, VARIANTS))
    for name, days in results.items():
        df = pd.DataFrame(days).T.drop(columns="max_abs_lychee_pos")
        df.loc["TOTAL"] = df.sum()
        print(f"\n=== {name} ===\n{df.round(0).to_string()}")
