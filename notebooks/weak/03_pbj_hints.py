# %% [markdown]
# # Rithik's hints: "PB is smooth, JELLY is bouncy" and "PB's book looks like FRUIT_BASKET's"
# Tests:
#   1. Do PEANUT_BUTTER and JELLY move together, or does one lead the other (a PB&J pair)?
#   2. Do PB and FRUIT_BASKET move together?
#   3. What makes a product look "smooth" vs "bouncy": spread vs tick volatility, quote noise.
#   4. Is JELLY's bounce noise around something slower (its own smoothed path, PB, or a 2,000 anchor)?
# Run from repo root:  python notebooks/weak/03_pbj_hints.py

# %%
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import data  # noqa: E402

OUT = os.path.join(data.ROOT, "outputs", "weak")
pd.set_option("display.width", 220)
P = data.prices()
mid = data.wide(P)
spread = data.wide(P, "spread")
day = pd.Series(mid.index // 10_000 - 2, index=mid.index)


def per_day_corr(x, y):
    out = []
    for d in (-2, -1, 0):
        s = (day == d) & x.notna() & y.notna()
        out.append(np.corrcoef(x[s], y[s])[0, 1])
    return out


# %% 1-2. co-movement at several horizons, per day
print("Correlation of price changes over h ticks, per day (d-2, d-1, d0):")
for a, b in (("PEANUT_BUTTER", "JELLY"), ("PEANUT_BUTTER", "FRUIT_BASKET"), ("JELLY", "FRUIT_BASKET")):
    for h in (1, 10, 100, 1000):
        cs = per_day_corr(mid[a].diff(h), mid[b].diff(h))
        print(f"  {a:14s} vs {b:13s} h={h:5d}: " + "  ".join(f"{c:+.3f}" for c in cs))

print("\nStrongest same-time correlates of PEANUT_BUTTER and JELLY among all 26 products (10-tick changes, all days):")
r10 = mid.diff(10)
for p in ("PEANUT_BUTTER", "JELLY"):
    c = r10.corr()[p].drop(p).sort_values(key=abs, ascending=False).head(5)
    print(f"  {p}: " + ", ".join(f"{k} {v:+.3f}" for k, v in c.items()))

print("\nLead-lag PB <-> JELLY: corr(A's last k-tick move, B's next k-tick move), per day")
for a, b in (("PEANUT_BUTTER", "JELLY"), ("JELLY", "PEANUT_BUTTER")):
    for k in (1, 5, 20, 100):
        cs = per_day_corr(mid[a].diff(k), mid[b].shift(-k) - mid[b])
        print(f"  {a} leads {b}, k={k:3d}: " + "  ".join(f"{c:+.3f}" for c in cs))

# %% 3. what "smooth" vs "bouncy" means in numbers
rows = []
for p in mid.columns:
    m = mid[p]; dm = m.diff().dropna()
    rows.append(dict(product=p, spread=spread[p].median(), tick_vol=dm.std(),
                     spread_over_tickvol=spread[p].median() / dm.std(),
                     ac1=dm.autocorr(1), pct_ticks_mid_moves=(dm != 0).mean(),
                     vol_100_per_tick=m.diff(100).std() / np.sqrt(100)))
sm = pd.DataFrame(rows).set_index("product").sort_values("spread_over_tickvol")
print("\nSmooth vs bouncy: spread relative to how much the mid moves each tick")
print(sm.round(3).to_string())

# %% 4. is JELLY's bounce noise around something slower?
j = mid["JELLY"]
fut = j.shift(-20)
cands = {
    "JELLY mid now": j,
    "JELLY EMA 10": j.ewm(span=10).mean(),
    "JELLY EMA 50": j.ewm(span=50).mean(),
    "anchor 2,000": pd.Series(2000.0, index=j.index),
    "0.9 mid + 0.1 x 2,000": 0.9 * j + 0.1 * 2000,
}
print("\nJELLY: mean abs error predicting the mid 20 ticks ahead, per day")
for name, pred in cands.items():
    errs = [((fut - pred).abs())[day == d].mean() for d in (-2, -1, 0)]
    print(f"  {name:22s}: " + "  ".join(f"{e:7.2f}" for e in errs))
# reversion toward 2,000: slope of next-1,000-tick change on (mid - 2,000), per day
for anchor in (2000, j.mean()):
    cs = []
    for d in (-2, -1, 0):
        s = (day == d) & j.shift(-1000).notna()
        x = (j - anchor)[s]; y = (j.shift(-1000) - j)[s]
        cs.append(np.polyfit(x, y, 1)[0])
    print(f"  JELLY slope of next-1000 change on (mid - {anchor:.0f}): " + "  ".join(f"{c:+.3f}" for c in cs))

# %% chart: PB and JELLY together, normalised
fig, axes = plt.subplots(2, 1, figsize=(12, 6))
z = (mid[["PEANUT_BUTTER", "JELLY", "FRUIT_BASKET"]] - mid[["PEANUT_BUTTER", "JELLY", "FRUIT_BASKET"]].mean()) / mid[["PEANUT_BUTTER", "JELLY", "FRUIT_BASKET"]].std()
for c in z.columns:
    axes[0].plot(z.index, z[c], lw=0.6, label=c)
axes[0].legend(fontsize=7); axes[0].set_title("Standardised mids (are they the same shape?)")
w = slice(5000, 5400)
for c, col in (("PEANUT_BUTTER", "C0"), ("JELLY", "C1")):
    sub = P[(P["product"] == c) & (P.t >= 5000) & (P.t < 5400)]
    axes[1].plot(sub.t, sub.mid_price - sub.mid_price.iloc[0], lw=0.8, color=col, label=f"{c} mid (from start of window)")
axes[1].legend(fontsize=7); axes[1].set_title("400-tick window: PB vs JELLY tick-by-tick")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "08_pb_jelly_basket.png"), dpi=100)
