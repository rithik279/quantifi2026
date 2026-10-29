# %% [markdown]
# # Standalone products: first exploration
# AMETHYST, TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM, JELLY, PEANUT_BUTTER.
# Run from the repo root:  python notebooks/standalone/01_explore.py
# Charts go to outputs/standalone/. Findings are summarised in NOTES.md next to this file.

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

OUT = os.path.join(data.ROOT, "outputs", "standalone")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)

PRODUCTS = ["AMETHYST", "TOFFEE_CAKE", "PAPER_LANTERNS", "TELLURIUM", "JELLY", "PEANUT_BUTTER"]
P = data.prices()
P = P[P["product"].isin(PRODUCTS)].copy()
T = data.trades()
T = T[T["symbol"].isin(PRODUCTS)].copy()
mid = data.wide(P)

# %% [markdown]
# ## 1. Price paths

# %%
fig, axes = plt.subplots(len(PRODUCTS), 1, figsize=(12, 2.2 * len(PRODUCTS)), sharex=True)
for ax, p in zip(axes, PRODUCTS):
    ax.plot(mid.index, mid[p], lw=0.6)
    ax.set_title(p, fontsize=9, loc="left")
    for b in (10_000, 20_000):
        ax.axvline(b, color="grey", lw=0.5, ls="--")
axes[-1].set_xlabel("global tick (day -2 | day -1 | day 0)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "01_price_paths.png"), dpi=110)

# %% [markdown]
# ## 2. Basic stats: spread, volatility, trade activity, mean reversion

# %%
def ar1_half_life(x: pd.Series) -> float:
    """Half-life (ticks) of deviations from the series' own mean, via AR(1) on levels."""
    x = x.dropna().to_numpy()
    d = x - x.mean()
    phi = np.dot(d[1:], d[:-1]) / np.dot(d[:-1], d[:-1])
    return np.log(0.5) / np.log(phi) if 0 < phi < 1 else np.inf


rows = []
for p in PRODUCTS:
    m = mid[p]
    dm = m.diff().dropna()
    g = P[P["product"] == p]
    tr = T[T["symbol"] == p]
    rows.append(dict(
        product=p,
        mean=m.mean(), std=m.std(), day_open_close=" / ".join(f"{m.iloc[i*10000]:.0f}-{m.iloc[i*10000+9999]:.0f}" for i in range(3)),
        spread_med=g["spread"].median(),
        tick_vol=dm.std(),
        ac1=dm.autocorr(1), ac2=dm.autocorr(2), ac5=dm.autocorr(5),
        vr_100=(m.diff(100).var() / (100 * dm.var())),  # variance ratio: <1 mean-reverting, >1 trending
        half_life=ar1_half_life(m),
        n_trades=len(tr), trades_per_day=len(tr) / 3, avg_qty=tr["quantity"].mean(),
        bid_vol1=g["bid_volume_1"].median(), ask_vol1=g["ask_volume_1"].median(),
    ))
stats = pd.DataFrame(rows).set_index("product")
print(stats.round(3).to_string())
stats.round(4).to_csv(os.path.join(OUT, "02_stats.csv"))

# %% [markdown]
# ## 3. Where do trades happen relative to the book?
# Classify each trade against the book at the same timestamp.

# %%
book = P[["day", "timestamp", "product", "bid_price_1", "ask_price_1", "bid_price_2", "ask_price_2", "mid_price"]]
TT = T.merge(book, left_on=["day", "timestamp", "symbol"], right_on=["day", "timestamp", "product"], how="left")
TT["loc"] = np.select(
    [TT.price >= TT.ask_price_1, TT.price <= TT.bid_price_1, (TT.price > TT.bid_price_1) & (TT.price < TT.ask_price_1)],
    ["at/above ask", "at/below bid", "inside"], "other")
TT["side"] = np.select([TT.price >= TT.ask_price_1, TT.price <= TT.bid_price_1], [1, -1], 0)
loc = pd.crosstab(TT["symbol"], TT["loc"], normalize="index").round(3)
print("\nTrade location vs book at same tick:\n", loc.to_string())
TT["dist_from_mid"] = TT.price - TT.mid_price
print("\nTrade price - mid (mean abs):\n", TT.groupby("symbol")["dist_from_mid"].apply(lambda s: s.abs().mean()).round(2).to_string())

# %% [markdown]
# ## 4. Adverse selection: does the mid move in the direction of the trade afterwards?
# For each aggressor-signed trade, mean future mid change (signed by trade side) at several horizons.
# Positive = the aggressor was informed (bad for a passive market maker on the other side).

# %%
mid_by_key = P.set_index(["day", "timestamp", "product"])["mid_price"]
res = {}
for p in PRODUCTS:
    m = mid[p].to_numpy()
    tr = TT[(TT.symbol == p) & (TT.side != 0)]
    out = {}
    for h in (1, 5, 20, 100, 500):
        idx = tr["t"].to_numpy()
        ok = idx + h < len(m)
        fwd = m[idx[ok] + h] - m[idx[ok]]
        out[f"h{h}"] = np.mean(fwd * tr["side"].to_numpy()[ok])
    out["n_signed"] = len(tr)
    res[p] = out
adv = pd.DataFrame(res).T
print("\nSigned future mid move after aggressive trades (coins):\n", adv.round(2).to_string())
adv.round(3).to_csv(os.path.join(OUT, "04_adverse_selection.csv"))

# %% [markdown]
# ## 5. Is there a stable 'wall' price? (largest-volume level per side)
# Market-making bots often quote big size at a fixed offset from the true value.
# If the wall mid is less noisy than the plain mid, it is a better fair-value estimate.

# %%
def wall_mid(g: pd.DataFrame) -> pd.Series:
    bp = g[["bid_price_1", "bid_price_2", "bid_price_3"]].to_numpy()
    bv = g[["bid_volume_1", "bid_volume_2", "bid_volume_3"]].fillna(-1).to_numpy()
    ap = g[["ask_price_1", "ask_price_2", "ask_price_3"]].to_numpy()
    av = g[["ask_volume_1", "ask_volume_2", "ask_volume_3"]].fillna(-1).to_numpy()
    wb = bp[np.arange(len(g)), bv.argmax(1)]
    wa = ap[np.arange(len(g)), av.argmax(1)]
    return pd.Series((wb + wa) / 2, index=g["t"].to_numpy())


wm = pd.DataFrame({p: wall_mid(P[P["product"] == p].sort_values("t")) for p in PRODUCTS})
cmp_rows = {}
for p in PRODUCTS:
    m, w = mid[p], wm[p]
    # Which is a better predictor of the mid 10 ticks ahead?
    fut = m.shift(-10)
    cmp_rows[p] = dict(
        mid_tick_std=m.diff().std(), wall_tick_std=w.diff().std(),
        err_mid=(fut - m).abs().mean(), err_wall=(fut - w).abs().mean(),
        err_ema20=(fut - m.ewm(span=20).mean()).abs().mean(),
    )
cmp = pd.DataFrame(cmp_rows).T
print("\nFair value candidates (mean abs error predicting mid 10 ticks ahead):\n", cmp.round(3).to_string())
cmp.round(4).to_csv(os.path.join(OUT, "05_fair_value_candidates.csv"))

# %% [markdown]
# ## 6. Spread / book shape snapshot per product

# %%
for p in PRODUCTS:
    g = P[P["product"] == p]
    print(f"\n{p}: spread distribution", g["spread"].value_counts(normalize=True).head(6).round(3).to_dict())
    print(f"   bid1 offset from mid", (g["mid_price"] - g["bid_price_1"]).value_counts(normalize=True).head(5).round(3).to_dict())
    if g["bid_price_2"].notna().any():
        print(f"   bid2 offset from mid", (g["mid_price"] - g["bid_price_2"]).value_counts(normalize=True).head(5).round(3).to_dict())

# %% TOFFEE_CAKE close-up: mean reversion around 5,000
fig, ax = plt.subplots(figsize=(12, 3))
ax.plot(mid.index, mid["TOFFEE_CAKE"], lw=0.5, label="mid")
ax.axhline(5000, color="red", lw=0.8, label="5,000")
ax.legend(); ax.set_title("TOFFEE_CAKE mid")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "06_toffee_mid.png"), dpi=110)

# %% TELLURIUM adverse selection chart
fig, ax = plt.subplots(figsize=(7, 3.5))
for p in PRODUCTS:
    ax.plot([1, 5, 20, 100, 500], adv.loc[p, ["h1", "h5", "h20", "h100", "h500"]], marker="o", label=p)
ax.set_xscale("log"); ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("ticks after trade"); ax.set_ylabel("signed mid move (coins)")
ax.set_title("Do aggressors know something? (adverse selection)")
ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "07_adverse_selection.png"), dpi=110)
print("\ncharts written to", OUT)
