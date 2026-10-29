# %% [markdown]
# # Standalone strategy diagnostics
# Where does PnL come from? Split every fill into "take" (crossed the book) vs "passive"
# (filled by a historical trade at our resting price) and measure the markout: how far the mid moves
# in our favour/against us N ticks after the fill. Run from repo root.

# %%
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import standalone  # noqa: E402

PRODUCTS = list(standalone.LIMITS)
pd.set_option("display.width", 200)


def diagnose(params=None, days=(-2, -1, 0), horizons=(10, 100)):
    res = bt.backtest(lambda: standalone.Trader(params), days, PRODUCTS, keep_fills=True)
    rows = []
    for d in res.days:
        data = bt.get_day(d.day, PRODUCTS)
        ts_index = {ts: i for i, ts in enumerate(data.timestamps)}
        for f in d.fills:
            i = ts_index[f["ts"]]
            m = data.mids[f["product"]]
            r = dict(day=d.day, product=f["product"], kind=f["kind"], qty=f["qty"],
                     edge=f["side"] * (m[i] - f["price"]))  # vs mid at fill time
            for h in horizons:
                r[f"markout{h}"] = f["side"] * (m[min(i + h, len(m) - 1)] - f["price"])
            rows.append(r)
    fills = pd.DataFrame(rows)
    agg = fills.assign(**{c: fills[c] * fills.qty for c in ["edge"] + [f"markout{h}" for h in horizons]}) \
        .groupby(["product", "kind"])[["qty", "edge"] + [f"markout{h}" for h in horizons]].sum()
    per_unit = agg.div(agg["qty"], axis=0).drop(columns="qty").add_suffix("/unit")
    return res, pd.concat([agg[["qty"]], per_unit], axis=1)


if __name__ == "__main__":
    res, table = diagnose()
    print(res.summary().round(0).to_string())
    print("\nFills by product and kind (per-unit edge vs mid, and markouts):")
    print(table.round(2).to_string())
