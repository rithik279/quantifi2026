# %% [markdown]
# # Pearls: first exploration
# WHITE, BLACK, GOLDEN, PINK, BLUE (limit 20 each). Hypothesis from the first pass: the five mids
# sum to ~50,000 and PINK does the correcting. Test that properly, then look for anything else.
# Run from repo root:  python notebooks/pearls/01_explore.py

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

OUT = os.path.join(data.ROOT, "outputs", "pearls")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)

PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
P = data.prices()
P = P[P["product"].isin(PEARLS)]
T = data.trades()
T = T[T["symbol"].isin(PEARLS)]
mid = data.wide(P)[PEARLS]
day = (mid.index // 10_000) - 2

# %% [markdown]
# ## 1. The sum constraint

# %%
S = mid.sum(axis=1)
print("sum of mids: mean %.2f  std %.2f  min %.1f  max %.1f" % (S.mean(), S.std(), S.min(), S.max()))
print("per day mean/std:\n", S.groupby(day).agg(["mean", "std"]).round(2).to_string())
dev = S - 50_000
print("deviation autocorr lag1/10/50:", [round(dev.autocorr(k), 3) for k in (1, 10, 50)])

# PCA on levels: the smallest-variance combination is the 'true' constraint
X = mid - mid.mean()
w, v = np.linalg.eigh(np.cov(X.T))
print("\nPCA eigenvalues (ascending):", np.round(w, 2))
print("smallest-variance direction (normalised to sum 5):", dict(zip(PEARLS, np.round(v[:, 0] / v[:, 0].sum() * 5, 3))))

fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
for p in PEARLS:
    axes[0].plot(mid.index, mid[p] - mid[p].iloc[0], lw=0.6, label=p)
axes[0].legend(fontsize=7); axes[0].set_title("Pearl mids (change from start)")
axes[1].plot(S.index, S, lw=0.5); axes[1].axhline(50_000, color="red", lw=0.6)
axes[1].set_title("Sum of the five mids")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_mids_and_sum.png"), dpi=110)

# %% [markdown]
# ## 2. Who corrects a deviation of the sum?
# Regress each pearl's future mid change on the current deviation (sum - 50,000).
# Slope near -1 = that pearl absorbs the whole gap.

# %%
rows = []
for h in (1, 5, 20, 50, 200):
    for p in PEARLS:
        fwd = mid[p].shift(-h) - mid[p]
        ok = fwd.notna()
        b = np.polyfit(dev[ok], fwd[ok], 1)[0]
        c = np.corrcoef(dev[ok], fwd[ok])[0, 1]
        rows.append(dict(h=h, product=p, slope=b, corr=c))
corr_tab = pd.DataFrame(rows).pivot(index="h", columns="product", values="slope")[PEARLS]
print("\nSlope of future mid change on (sum - 50,000):\n", corr_tab.round(3).to_string())
corr_tab.round(4).to_csv(os.path.join(OUT, "02_who_corrects_slope.csv"))

# %% [markdown]
# ## 3. Is it 50,000 exactly, or does each pearl have its own fair value given the others?
# Fair value of pearl i = 50,000 - sum(other mids). Compare that to its own mid as a predictor.

# %%
rows = []
for p in PEARLS:
    implied = 50_000 - (S - mid[p])
    fut = mid[p].shift(-10)
    rows.append(dict(product=p,
                     gap_mean=(implied - mid[p]).mean(), gap_std=(implied - mid[p]).std(),
                     err_own_mid=(fut - mid[p]).abs().mean(),
                     err_implied=(fut - implied).abs().mean(),
                     err_blend=(fut - (0.5 * mid[p] + 0.5 * implied)).abs().mean()))
imp = pd.DataFrame(rows).set_index("product")
print("\nImplied fair value (50,000 - others) vs own mid, error predicting mid 10 ticks ahead:\n", imp.round(3).to_string())

# %% [markdown]
# ## 4. Return correlations and lead-lag

# %%
for h in (1, 10, 100):
    r = mid.diff(h).dropna()
    print(f"\nReturn correlation at {h}-tick horizon:\n", r.corr().round(2).to_string())

r1 = mid.diff()
print("\nLead-lag: corr(ret_i[t], ret_j[t+1]) (row leads column):")
ll = pd.DataFrame({j: {i: r1[i].corr(r1[j].shift(-1)) for i in PEARLS} for j in PEARLS})
print(ll.round(3).to_string())

# %% [markdown]
# ## 5. Per-pearl behaviour: spread, noise, trend, mean reversion, trade activity

# %%
rows = []
for p in PEARLS:
    m = mid[p]; dm = m.diff().dropna(); g = P[P["product"] == p]; tr = T[T["symbol"] == p]
    rows.append(dict(product=p, spread_med=g.spread.median(), tick_vol=dm.std(), ac1=dm.autocorr(1),
                     vr_100=m.diff(100).var() / (100 * dm.var()), n_trades=len(tr), avg_qty=tr.quantity.mean(),
                     n_unique_mids=m.nunique(), pct_ticks_mid_unchanged=(dm == 0).mean()))
beh = pd.DataFrame(rows).set_index("product")
print("\n", beh.round(3).to_string())
beh.round(4).to_csv(os.path.join(OUT, "03_behaviour.csv"))

# %% [markdown]
# ## 6. GOLDEN_PEARLS staircase: which levels and how long does it sit on each?

# %%
g = mid["GOLDEN_PEARLS"]
print("\nGOLDEN mid value counts (top 12):\n", g.value_counts().head(12).to_string())
fig, ax = plt.subplots(figsize=(12, 3))
ax.plot(g.index, g, lw=0.6)
ax.set_title("GOLDEN_PEARLS mid")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "04_golden_steps.png"), dpi=110)

runs = (g != g.shift()).cumsum()
rl = g.groupby(runs).agg(["first", "size"])
print("\nLongest GOLDEN plateaus:\n", rl.sort_values("size", ascending=False).head(10).to_string())

# %% [markdown]
# ## 7. Trades: where they print vs the book, and adverse selection

# %%
book = P[["t", "product", "bid_price_1", "ask_price_1", "mid_price"]]
TT = T.merge(book, left_on=["t", "symbol"], right_on=["t", "product"])
TT["side"] = np.select([TT.price >= TT.ask_price_1, TT.price <= TT.bid_price_1], [1, -1], 0)
print("\nfraction of trades at/through the touch:", TT.groupby("symbol").side.apply(lambda s: (s != 0).mean()).round(3).to_dict())
res = {}
for p in PEARLS:
    m = mid[p].to_numpy(); tr = TT[(TT.symbol == p) & (TT.side != 0)]
    res[p] = {f"h{h}": np.mean((m[np.minimum(tr.t.to_numpy() + h, len(m) - 1)] - m[tr.t.to_numpy()]) * tr.side.to_numpy()) for h in (1, 5, 20, 100)}
print("\nSigned mid move after aggressive trades:\n", pd.DataFrame(res).T.round(2).to_string())

# %% PINK vs implied chart (zoom on a window)
w = slice(5_000, 6_000)
fig, ax = plt.subplots(figsize=(12, 3))
implied_pink = 50_000 - (S - mid["PINK_PEARLS"])
ax.plot(mid.index[w], mid["PINK_PEARLS"].iloc[w], lw=0.8, label="PINK mid")
ax.plot(mid.index[w], implied_pink.iloc[w], lw=0.8, label="50,000 - other four")
ax.legend(); ax.set_title("PINK tracks the 'implied' value (1,000-tick window)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "05_pink_vs_implied.png"), dpi=110)
print("charts written to", OUT)
