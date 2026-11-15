# %% [markdown]
# # TELLURIUM: can we use the informed flow instead of being run over by it?
# What we can actually see: at tick t we get market_trades from tick t-1. So every signal here is
# measured from the tick AFTER the trade, which is when our trader could react.

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
P = data.prices()
T = data.trades()
p = "TELLURIUM"
g = P[P["product"] == p].sort_values("t").reset_index(drop=True)
tr = T[T["symbol"] == p].merge(g[["t", "bid_price_1", "ask_price_1", "bid_price_2", "ask_price_2", "mid_price"]], on="t")
tr["side"] = np.select([tr.price >= tr.ask_price_1, tr.price <= tr.bid_price_1], [1, -1], 0)
tr["beyond_touch"] = (tr.price > tr.ask_price_1) | (tr.price < tr.bid_price_1)
print("trades beyond the touch (sweeps):", round(tr.beyond_touch.mean(), 3))
print("trade qty distribution:", tr.quantity.value_counts().sort_index().to_dict())

# %% Sign persistence: is the next trade likely in the same direction?
s = tr.side.to_numpy()
print("P(next trade same side) =", round(np.mean(s[1:] == s[:-1]), 3))

# %% Signed flow per tick -> future mid move measured from the NEXT tick (what we can trade on)
n = len(g)
flow = np.zeros(n)
np.add.at(flow, tr.t.to_numpy(), (tr.side * tr.quantity).to_numpy())
m = g.mid_price.to_numpy()
rows = []
for k in (1, 5, 20):  # flow summed over the last k ticks (ending at t-1)
    f = pd.Series(flow).rolling(k).sum().shift(1).to_numpy()  # info available at tick t
    for h in (1, 5, 20, 100):
        fwd = np.r_[m[h:] - m[:-h], np.full(h, np.nan)]
        ok = ~np.isnan(f) & ~np.isnan(fwd) & (f != 0)
        c = np.corrcoef(f[ok], fwd[ok])[0, 1]
        # conditional mean move when flow is strongly positive / negative
        hi = ok & (f >= np.nanpercentile(f[ok], 90))
        lo = ok & (f <= np.nanpercentile(f[ok], 10))
        rows.append(dict(window=k, horizon=h, corr=c, move_if_buy_flow=np.mean(fwd[hi]), move_if_sell_flow=np.mean(fwd[lo]), n=ok.sum()))
sig = pd.DataFrame(rows)
print("\nSigned flow (seen at t) -> mid move t..t+h\n", sig.round(3).to_string(index=False))
sig.round(4).to_csv(os.path.join(OUT, "08_tellurium_flow_signal.csv"), index=False)

# %% Does the book itself lead? Order-book imbalance at touch -> future move
imb = (g.bid_volume_1 - g.ask_volume_1) / (g.bid_volume_1 + g.ask_volume_1)
for h in (1, 5, 20):
    fwd = pd.Series(m).shift(-h) - pd.Series(m)
    print(f"book imbalance -> {h}-tick move corr: {imb.corr(fwd):.3f}")

# %% Microprice vs mid as fair value
micro = (g.bid_price_1 * g.ask_volume_1 + g.ask_price_1 * g.bid_volume_1) / (g.bid_volume_1 + g.ask_volume_1)
fut = pd.Series(m).shift(-10)
print("err mid->t+10:", (fut - m).abs().mean().round(3), " err micro->t+10:", (fut - micro).abs().mean().round(3))

# %% Crossing cost vs expected move: is a taker strategy viable?
half_spread = (g.ask_price_1 - g.bid_price_1).mean() / 2
print(f"\nmean half-spread {half_spread:.2f}: a taker needs a predicted move bigger than this")

# %% Plot: move after flow seen
fig, ax = plt.subplots(figsize=(7, 3.5))
for k in (1, 5, 20):
    d = sig[sig.window == k]
    ax.plot(d.horizon, d.move_if_buy_flow, marker="o", label=f"top-10% buy flow, last {k} ticks")
    ax.plot(d.horizon, d.move_if_sell_flow, marker="x", ls="--", label=f"top-10% sell flow, last {k} ticks")
ax.axhline(half_spread, color="grey", lw=0.6, ls=":"); ax.axhline(-half_spread, color="grey", lw=0.6, ls=":")
ax.set_xscale("log"); ax.set_xlabel("horizon (ticks, from when we can see the flow)"); ax.set_ylabel("mid move")
ax.set_title("TELLURIUM: mid move after strong flow (dotted = half-spread)")
ax.legend(fontsize=6)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "09_tellurium_flow.png"), dpi=110)
