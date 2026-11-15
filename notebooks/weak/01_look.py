# %% [markdown]
# # The weak products, visually, plus a scan for angles we haven't tried
# JELLY, PEANUT_BUTTER, WHITE/BLACK/BLUE/GOLDEN pearls, the basket and its fruits, TELLURIUM.
# Charts (outputs/weak/):
#   01_paths.png            full three days of each mid
#   02_intraday_overlay.png the three days on top of each other (same clock) -> time-of-day patterns?
#   03_zoom_trades.png      400 ticks of best bid/ask with every trade marked (green = buyer hit the ask)
#   04_trend_or_revert.png  variance ratio by horizon, per day: <1 snaps back, >1 trends, =1 random
# Scans (printed + CSV): cross-product lead-lag over ALL 26 products; order-book imbalance; trade flow.
# Run from repo root:  python notebooks/weak/01_look.py

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
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250)

WEAK = ["JELLY", "PEANUT_BUTTER", "WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS", "GOLDEN_PEARLS",
        "FRUIT_BASKET", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN", "TELLURIUM"]
P = data.prices()
T = data.trades()
mid = data.wide(P)
bid = data.wide(P, "bid_price_1")
ask = data.wide(P, "ask_price_1")
bv = data.wide(P, "bid_volume_1")
av = data.wide(P, "ask_volume_1")
day = pd.Series(mid.index // 10_000 - 2, index=mid.index)
ALL = list(mid.columns)

# signed trades: +qty if the buyer lifted the ask, -qty if the seller hit the bid
TT = T.merge(P[["t", "product", "bid_price_1", "ask_price_1"]], left_on=["t", "symbol"], right_on=["t", "product"])
TT["side"] = np.select([TT.price >= TT.ask_price_1, TT.price <= TT.bid_price_1], [1, -1], 0)


def grid(n, w=4.2, h=2.4, cols=3):
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(w * cols, h * rows), squeeze=False)
    return fig, axes.ravel()


# %% 1. full paths
fig, axes = grid(len(WEAK))
for ax, p in zip(axes, WEAK):
    ax.plot(mid.index, mid[p], lw=0.5)
    for b in (10_000, 20_000):
        ax.axvline(b, color="grey", lw=0.5, ls="--")
    ax.set_title(p, fontsize=9); ax.tick_params(labelsize=7)
for ax in axes[len(WEAK):]:
    ax.axis("off")
fig.suptitle("Mid price, days -2 | -1 | 0", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "01_paths.png"), dpi=95); plt.close(fig)

# %% 2. intraday overlay (each day shifted to start at 0)
fig, axes = grid(len(WEAK))
cors = {}
for ax, p in zip(axes, WEAK):
    paths = []
    for d, c in zip((-2, -1, 0), ("C0", "C1", "C2")):
        m = mid[p][day == d].to_numpy()
        m = m - m[0]
        paths.append(m)
        ax.plot(np.arange(len(m)), m, lw=0.6, color=c, label=f"day {d}")
    cors[p] = np.mean([np.corrcoef(np.diff(paths[a]), np.diff(paths[b]))[0, 1] for a, b in ((0, 1), (0, 2), (1, 2))])
    ax.set_title(f"{p}  (avg day-to-day corr of moves {cors[p]:+.3f})", fontsize=8); ax.tick_params(labelsize=7)
axes[0].legend(fontsize=6)
for ax in axes[len(WEAK):]:
    ax.axis("off")
fig.suptitle("The three days on the same clock (change from the day's open)", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_intraday_overlay.png"), dpi=95); plt.close(fig)

# %% 3. zoom with trades (a busy 400-tick window on day 0)
fig, axes = grid(len(WEAK), w=4.6, h=2.6)
for ax, p in zip(axes, WEAK):
    tr = TT[(TT.symbol == p) & (TT.day == 0)]
    centre = int(tr.t.median()) if len(tr) else 25_000
    lo, hi = centre - 200, centre + 200
    w = slice(lo, hi)
    ax.step(mid.index[lo:hi], bid[p].loc[lo:hi - 1], where="post", lw=0.7, color="tab:blue", label="best bid")
    ax.step(mid.index[lo:hi], ask[p].loc[lo:hi - 1], where="post", lw=0.7, color="tab:red", label="best ask")
    z = tr[(tr.t >= lo) & (tr.t < hi)]
    ax.scatter(z[z.side == 1].t, z[z.side == 1].price, marker="^", s=18, color="green", zorder=3, label="buyer lifts ask")
    ax.scatter(z[z.side == -1].t, z[z.side == -1].price, marker="v", s=18, color="black", zorder=3, label="seller hits bid")
    ax.set_title(f"{p}: ticks {lo}-{hi}", fontsize=8); ax.tick_params(labelsize=6)
axes[0].legend(fontsize=5)
for ax in axes[len(WEAK):]:
    ax.axis("off")
fig.suptitle("Close-up of the book: best bid/ask and every trade", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_zoom_trades.png"), dpi=95); plt.close(fig)

# %% 4. variance ratio by horizon and day
H = [2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]
fig, axes = grid(len(WEAK))
vr_rows = []
for ax, p in zip(axes, WEAK):
    for d, c in zip((-2, -1, 0), ("C0", "C1", "C2")):
        m = mid[p][day == d]
        v1 = m.diff().var()
        vr = [m.diff(h).var() / (h * v1) for h in H]
        ax.plot(H, vr, marker="o", ms=3, color=c, lw=0.8, label=f"day {d}")
        vr_rows.append(dict(product=p, day=d, **{f"h{h}": v for h, v in zip(H, vr)}))
    ax.axhline(1, color="k", lw=0.5); ax.set_xscale("log")
    ax.set_title(p, fontsize=9); ax.tick_params(labelsize=7)
axes[0].legend(fontsize=6)
for ax in axes[len(WEAK):]:
    ax.axis("off")
fig.suptitle("Variance ratio by horizon (ticks): below 1 = snaps back, above 1 = trends", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "04_trend_or_revert.png"), dpi=95); plt.close(fig)
pd.DataFrame(vr_rows).round(3).to_csv(os.path.join(OUT, "04_variance_ratio.csv"), index=False)

# %% 5. scan: does ANY product's recent move predict a weak product's next move? (same sign every day)
rows = []
for k in (1, 5, 20, 100):
    past = mid.diff(k)
    fut = mid.shift(-k) - mid
    for j in WEAK:
        for i in ALL:
            cs = []
            for d in (-2, -1, 0):
                sel = (day == d) & past[i].notna() & fut[j].notna()
                cs.append(np.corrcoef(past[i][sel], fut[j][sel])[0, 1])
            if np.sign(cs[0]) == np.sign(cs[1]) == np.sign(cs[2]):
                rows.append(dict(target=j, predictor=i, k=k, d_2=cs[0], d_1=cs[1], d0=cs[2], weakest=min(np.abs(cs))))
LL = pd.DataFrame(rows).sort_values("weakest", ascending=False)
LL.round(3).to_csv(os.path.join(OUT, "05_leadlag_scan.csv"), index=False)
print("Lead-lag scan: corr(predictor's last k-tick move, target's next k-tick move), same sign on all 3 days")
print("(predictor == target means momentum/reversal of the product itself)")
print(LL[LL.weakest > 0.03].head(30).round(3).to_string(index=False))

# %% 6. scan: order-book imbalance and trade flow -> next move, per day
rows = []
for p in WEAK:
    imb = (bv[p] - av[p]) / (bv[p] + av[p])
    flow = pd.Series(0.0, index=mid.index)
    tr = TT[(TT.symbol == p) & (TT.side != 0)]
    np.add.at(flow.values, tr.t.to_numpy(), (tr.side * tr.quantity).to_numpy())
    for name, sig in (("imbalance", imb), ("flow_last5", flow.rolling(5).sum().shift(1)),
                      ("flow_last50", flow.rolling(50).sum().shift(1)), ("flow_last500", flow.rolling(500).sum().shift(1))):
        for h in (5, 50, 500):
            fut = mid[p].shift(-h) - mid[p]
            cs = []
            for d in (-2, -1, 0):
                sel = (day == d) & sig.notna() & fut.notna()
                cs.append(np.corrcoef(sig[sel], fut[sel])[0, 1])
            rows.append(dict(product=p, signal=name, h=h, d_2=cs[0], d_1=cs[1], d0=cs[2],
                             consistent=np.sign(cs[0]) == np.sign(cs[1]) == np.sign(cs[2])))
SIG = pd.DataFrame(rows)
SIG.round(3).to_csv(os.path.join(OUT, "06_book_and_flow_signals.csv"), index=False)
print("\nOrder-book imbalance and trade flow -> next h-tick move (corr per day), consistent ones with |corr| > 0.03:")
s = SIG[SIG.consistent & (SIG[["d_2", "d_1", "d0"]].abs().min(axis=1) > 0.03)]
print(s.round(3).to_string(index=False))

print("\nAverage day-to-day correlation of moves on the same clock (time-of-day pattern?):")
print({k: round(v, 3) for k, v in cors.items()})
