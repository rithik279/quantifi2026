# %% [markdown]
# # PEANUT_BUTTER: can aggressive market making work?
# Idea (Rithik): PB looks efficient with a tight spread, so quote as tightly as possible around the mid
# and trade as much as possible. With no transaction costs, even a slim edge per trade adds up.
#
# The question this answers: what actually limits PB market-making PnL in this backtest?
#   1. How much volume is there to trade against? (passive fills only happen when a historical trade
#      prints at our price or better)
#   2. How much of it do we capture, and at what edge?
#   3. What eats the edge: adverse selection (price moves against us after a fill) or inventory drift?
# Run from repo root:  python notebooks/weak/02_peanut_butter_mm.py

# %%
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import data  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
P_ = "PEANUT_BUTTER"
pd.set_option("display.width", 220)

# %% 1. how much is there to trade?
T = data.trades()
P = data.prices()
tr = T[T.symbol == P_].merge(P[P["product"] == P_][["t", "bid_price_1", "ask_price_1", "mid_price"]], on="t")
tr["side"] = np.select([tr.price >= tr.ask_price_1, tr.price <= tr.bid_price_1], [1, -1], 0)
avail = tr.groupby("day").agg(trades=("quantity", "size"), units=("quantity", "sum"))
avail["units_at_bid"] = tr[tr.side == -1].groupby("day").quantity.sum()
avail["units_at_ask"] = tr[tr.side == 1].groupby("day").quantity.sum()
print("Volume available to a passive market maker (historical trades):")
print(avail.to_string())
half_spread = (P[P["product"] == P_].spread / 2).mean()
print(f"mean half-spread {half_spread:.2f}: the most a perfect market maker earns per unit, before price moves")
print(f"=> ceiling on spread capture ~ {avail.units.mean() * half_spread:,.0f} coins/day if every unit filled and the price never moved\n")

# %% 2. variants of the idea
BASE = dict(fair="mid", take_edge=100, make_edge=3, skew=5, soft_cap=10)  # current
VARIANTS = {
    "current (touch, cap 10, skew 5)": BASE,
    "max size (cap 50, skew 0)": dict(BASE, soft_cap=50, skew=0),
    "max size + skew 5": dict(BASE, soft_cap=50, skew=5),
    "tight: fair=mid, make_edge 0.5": dict(BASE, make_edge=0.5, soft_cap=50, skew=5),
    "penny 1 inside the touch": dict(BASE, make_edge=0.5, improve=1, soft_cap=50, skew=5),
    "penny 2 inside the touch": dict(BASE, make_edge=0.5, improve=2, soft_cap=50, skew=5),
}

rows = []
for name, prm in VARIANTS.items():
    res = bt.backtest(lambda: standalone.Trader({P_: prm}), (-2, -1, 0), [P_], keep_fills=True, record_every=0)
    for d in res.days:
        dd = bt.get_day(d.day, [P_])
        idx = {ts: i for i, ts in enumerate(dd.timestamps)}
        m = dd.mids[P_]
        f = pd.DataFrame(d.fills)
        if len(f):
            i = f.ts.map(idx).to_numpy()
            edge = (f.side * (m[i] - f.price) * f.qty).sum()
            mk100 = (f.side * (m[np.minimum(i + 100, len(m) - 1)] - f.price) * f.qty).sum()
        else:
            edge = mk100 = 0.0
        rows.append(dict(variant=name, day=d.day, pnl=d.total, units=int(f.qty.sum()) if len(f) else 0,
                         edge_at_fill=edge, after_100_ticks=mk100, final_pos=d.final_position.get(P_, 0)))
df = pd.DataFrame(rows)
df["share_of_volume"] = df.units / df.day.map(avail.units)
summ = df.groupby("variant", sort=False).agg(pnl_total=("pnl", "sum"), pnl_d_2=("pnl", "first"), pnl_d0=("pnl", "last"),
                                             units=("units", "sum"), share_of_volume=("share_of_volume", "mean"),
                                             edge_at_fill=("edge_at_fill", "sum"), after_100_ticks=("after_100_ticks", "sum"))
summ["edge_per_unit"] = summ.edge_at_fill / summ.units
summ["kept_after_100_per_unit"] = summ.after_100_ticks / summ.units
print("Variants over days -2..0:")
print(summ.round(2).to_string())
df.round(1).to_csv(os.path.join(OUT, "07_peanut_butter_mm_variants.csv"), index=False)
print("\nPer day PnL:")
print(df.pivot(index="variant", columns="day", values="pnl").round(0).to_string())
