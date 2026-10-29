# %% [markdown]
# # Basket: first exploration
# FRUIT_BASKET vs DRAGONFRUIT, GRANADILLA, MANGOSTEEN (all limit 40).
# Questions: (1) what are the weights? (2) how does the premium (basket - NAV) behave?
# (3) which leg does the correcting, the basket or the fruits? (4) is it tradable after spreads?
# Run from repo root:  python notebooks/basket/01_explore.py

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

OUT = os.path.join(data.ROOT, "outputs", "basket")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)

FRUITS = ["DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"]
B = "FRUIT_BASKET"
ALL = [B] + FRUITS
P = data.prices()
P = P[P["product"].isin(ALL)]
T = data.trades()
T = T[T["symbol"].isin(ALL)]
mid = data.wide(P)[ALL]
day = (mid.index // 10_000) - 2

# %% [markdown]
# ## 1. Weights: regress basket on fruits, in levels and in changes at several horizons

# %%
def ols(y, X):
    X1 = np.column_stack([X, np.ones(len(X))])
    coef, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ coef
    return coef, 1 - resid.var() / y.var()


rows = []
c, r2 = ols(mid[B].to_numpy(), mid[FRUITS].to_numpy())
rows.append(dict(spec="levels, all days", D=c[0], G=c[1], M=c[2], const=c[3], r2=r2))
for d in (-2, -1, 0):
    m = mid[day == d]
    c, r2 = ols(m[B].to_numpy(), m[FRUITS].to_numpy())
    rows.append(dict(spec=f"levels, day {d}", D=c[0], G=c[1], M=c[2], const=c[3], r2=r2))
for h in (1, 10, 100, 500):
    dm = mid.diff(h).dropna()
    c, r2 = ols(dm[B].to_numpy(), dm[FRUITS].to_numpy())
    rows.append(dict(spec=f"{h}-tick changes", D=c[0], G=c[1], M=c[2], const=c[3], r2=r2))
wt = pd.DataFrame(rows).set_index("spec")
print("Basket ~ D, G, M:\n", wt.round(3).to_string())
wt.round(4).to_csv(os.path.join(OUT, "01_weight_regressions.csv"))

# Try candidate integer weight sets: which makes the premium most stable (lowest tick-change std)?
cands = [(1, 1, 1), (2, 3, 1), (4, 6, 1), (2, 2, 1), (1, 2, 1), (2, 4, 1), (3, 3, 1), (2, 3, 2)]
rows = []
for w in cands:
    nav = mid[FRUITS] @ np.array(w)
    prem = mid[B] - nav
    rows.append(dict(weights=w, prem_mean=prem.mean(), prem_std=prem.std(), prem_change_std=prem.diff().std(),
                     prem_change100_std=prem.diff(100).std()))
print("\nCandidate integer weights:\n", pd.DataFrame(rows).round(2).to_string(index=False))

# %% [markdown]
# ## 2. The premium (basket - 2D - 3G - 1M)

# %%
W = np.array([2, 3, 1])
nav = mid[FRUITS] @ W
prem = mid[B] - nav
print("\npremium per day:\n", prem.groupby(day).agg(["mean", "std", "min", "max"]).round(1).to_string())
d = prem - prem.mean()
phi = np.dot(d[1:], d[:-1]) / np.dot(d[:-1], d[:-1])
print(f"AR(1) phi of premium level: {phi:.5f}  -> half-life {np.log(0.5) / np.log(phi):.0f} ticks")
for win in (200, 1000, 3000):
    z = (prem - prem.rolling(win).mean())
    zz = z / prem.rolling(win).std()
    fwd = prem.shift(-200) - prem
    ok = zz.notna() & fwd.notna()
    print(f"rolling {win}: corr(z, next-200-tick premium change) = {np.corrcoef(zz[ok], fwd[ok])[0, 1]:.3f}")

fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
axes[0].plot(mid.index, mid[B], lw=0.6, label="FRUIT_BASKET")
axes[0].plot(mid.index, nav, lw=0.6, label="2D + 3G + 1M")
axes[0].legend(); axes[0].set_title("Basket vs NAV")
axes[1].plot(mid.index, prem, lw=0.5, label="premium")
axes[1].plot(mid.index, prem.rolling(1000).mean(), lw=1, label="rolling 1000 mean")
axes[1].legend(); axes[1].set_title("Premium = basket - NAV")
for ax in axes:
    for b in (10_000, 20_000):
        ax.axvline(b, color="grey", lw=0.5, ls="--")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_basket_vs_nav.png"), dpi=110)

# %% [markdown]
# ## 3. Which leg corrects? Regress future changes of basket and NAV on the premium deviation

# %%
dev = prem - prem.rolling(1000, min_periods=100).mean()
rows = []
for h in (10, 50, 200, 1000):
    for name, s in (("basket", mid[B]), ("nav", nav)):
        fwd = s.shift(-h) - s
        ok = dev.notna() & fwd.notna()
        rows.append(dict(h=h, leg=name, slope=np.polyfit(dev[ok], fwd[ok], 1)[0]))
print("\nSlope of future change on premium deviation (from rolling-1000 mean):\n",
      pd.DataFrame(rows).pivot(index="h", columns="leg", values="slope").round(3).to_string())

# Lead-lag at tick level
rb, rn = mid[B].diff(), nav.diff()
print("\ncorr(basket ret t, nav ret t)   =", round(rb.corr(rn), 3))
print("corr(nav ret t, basket ret t+1) =", round(rn.corr(rb.shift(-1)), 3), "(NAV leads basket?)")
print("corr(basket ret t, nav ret t+1) =", round(rb.corr(rn.shift(-1)), 3), "(basket leads NAV?)")
for k in (1, 5, 20):
    print(f"corr(nav ret over last {k}, basket ret next {k}) =", round(nav.diff(k).corr(mid[B].shift(-k) - mid[B]), 3))

# %% [markdown]
# ## 4. Per-product behaviour and trading cost

# %%
rows = []
for p in ALL:
    m = mid[p]; dm = m.diff().dropna(); g = P[P["product"] == p]; tr = T[T["symbol"] == p]
    rows.append(dict(product=p, spread_med=g.spread.median(), tick_vol=dm.std(), ac1=dm.autocorr(1),
                     vr_100=m.diff(100).var() / (100 * dm.var()), trades_per_day=len(tr) / 3, avg_qty=tr.quantity.mean(),
                     top_vol=g.bid_volume_1.median()))
beh = pd.DataFrame(rows).set_index("product")
print("\n", beh.round(3).to_string())
half = beh.spread_med / 2
cost = half[B] + (W * half[FRUITS].to_numpy()).sum()
print(f"\nCost to cross the whole hedge once (basket + 2D + 3G + 1M half-spreads): {cost:.1f} coins")
print(f"Premium std within a day: ~{prem.groupby(day).std().mean():.0f} coins")
