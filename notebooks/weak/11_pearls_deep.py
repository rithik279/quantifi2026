# %% [markdown]
# # Pearls deep dive: WHITE, BLACK, BLUE, GOLDEN (PINK is already solved by the sum rule)
# A. Can the five pearls predict each other? Linear model of each pearl's next-h move on every
#    pearl's recent moves, the sum deviation and short-term deviations. Fit on days -2/-1, test on day 0,
#    and compare with an own-history-only model to see whether the OTHER pearls add anything.
# B. Trade impact: after an aggressive trade in pearl i, how do pearls j move?
# C. GOLDEN's three steps: what do the others do around them, and is there any warning beforehand?
# D. Is any predicted move big enough to matter against each pearl's spread?
# Run from repo root:  python notebooks/weak/11_pearls_deep.py

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
pd.set_option("display.width", 230)
PE = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
SHORT = {p: p.split("_")[0][:5] for p in PE}
P = data.prices()
T = data.trades()
mid = data.wide(P, products=PE)[PE]
spread = data.wide(P, "spread", products=PE)[PE]
day = pd.Series(mid.index // 10_000 - 2, index=mid.index)
dev = mid.sum(axis=1) - 50_000

# %% A. features (past only) and targets
X = pd.DataFrame(index=mid.index)
for p in PE:
    s = SHORT[p]
    for k in (1, 5, 20):
        X[f"{s}_r{k}"] = mid[p].diff(k)
    X[f"{s}_ema20gap"] = mid[p] - mid[p].ewm(span=20).mean()
X["sumdev"] = dev
X["sumdev_r5"] = dev.diff(5)
own_cols = {p: [c for c in X.columns if c.startswith(SHORT[p] + "_")] + ["sumdev", "sumdev_r5"] for p in PE}


def fit_eval(cols, y):
    ok = X[cols].notna().all(axis=1) & y.notna()
    tr = ok & day.isin([-2, -1]); te = ok & (day == 0)
    A = np.column_stack([X.loc[tr, cols].to_numpy(), np.ones(tr.sum())])
    coef, *_ = np.linalg.lstsq(A, y[tr].to_numpy(), rcond=None)
    pred = pd.Series(np.column_stack([X[cols].to_numpy(), np.ones(len(X))]) @ coef, index=X.index)
    r2 = lambda m: 1 - ((y[m] - pred[m]) ** 2).sum() / ((y[m] - y[m].mean()) ** 2).sum()  # noqa: E731
    per_day = [np.corrcoef(pred[ok & (day == d)], y[ok & (day == d)])[0, 1] for d in (-2, -1, 0)]
    return dict(train_r2=r2(tr), test_r2=r2(te), corr_d_2=per_day[0], corr_d_1=per_day[1], corr_d0=per_day[2]), coef, pred


rows, preds = [], {}
for p in PE:
    for h in (5, 20, 100):
        y = mid[p].shift(-h) - mid[p]
        all_cols = list(X.columns)
        m_all, coef, pred = fit_eval(all_cols, y)
        m_own, _, _ = fit_eval(own_cols[p], y)
        rows.append(dict(pearl=p, h=h, model="all pearls", **m_all))
        rows.append(dict(pearl=p, h=h, model="own + sum only", **m_own))
        preds[(p, h)] = pred
        if h == 20:
            top = sorted(zip(all_cols, coef[:-1]), key=lambda kv: -abs(kv[1]) * X[kv[0]].std())[:4]
            print(f"{p} h=20 biggest drivers (coef x std): " + ", ".join(f"{c} {v * X[c].std():+.2f}" for c, v in top))
A = pd.DataFrame(rows)
A.round(3).to_csv(os.path.join(OUT, "18_pearls_predictive_models.csv"), index=False)
print("\nA. Predicting each pearl's next-h move. Fit on days -2/-1; test_r2 and corr_d0 are out-of-sample:")
print(A.round(3).to_string(index=False))

# %% B. trade impact matrix
TT = T[T.symbol.isin(PE)].merge(P[["t", "product", "bid_price_1", "ask_price_1"]], left_on=["t", "symbol"], right_on=["t", "product"])
TT["side"] = np.select([TT.price >= TT.ask_price_1, TT.price <= TT.bid_price_1], [1, -1], 0)
print("\nB. Mean move of pearl j (column) over the next 20 ticks after an aggressive trade in pearl i (row), "
      "signed by the trade's side. Per day: d-2 / d-1 / d0")
mat = {}
for i in PE:
    ev = TT[(TT.symbol == i) & (TT.side != 0)]
    mat[SHORT[i]] = {}
    for j in PE:
        cells = []
        for d in (-2, -1, 0):
            e = ev[ev.day == d]
            idx = e.t.to_numpy()
            ok = idx + 20 < len(mid)
            mv = (mid[j].to_numpy()[idx[ok] + 20] - mid[j].to_numpy()[idx[ok]]) * e.side.to_numpy()[ok]
            cells.append(mv.mean() if len(mv) else np.nan)
        mat[SHORT[i]][SHORT[j]] = " / ".join(f"{c:+.1f}" for c in cells)
print(pd.DataFrame(mat).T.to_string())

# %% C. GOLDEN steps
g = mid["GOLDEN_PEARLS"]
lvl = (g / 50).round() * 50
on_level = (g - lvl).abs() <= 0.5
plateau = lvl.where(on_level).ffill()
steps = plateau[plateau.diff().abs() > 0].index.tolist()
print(f"\nC. GOLDEN plateau changes at ticks {steps}: " + ", ".join(f"{plateau[s - 1]:.0f}->{plateau[s]:.0f}" for s in steps))
fig, axes = plt.subplots(len(steps), 1, figsize=(12, 3.2 * len(steps)), squeeze=False)
for ax, s in zip(axes[:, 0], steps):
    lo, hi = max(0, s - 400), min(len(mid), s + 600)
    for p in PE:
        ax.plot(mid.index[lo:hi], mid[p].iloc[lo:hi] - mid[p].iloc[lo], lw=0.7, label=SHORT[p])
    ax.plot(mid.index[lo:hi], dev.iloc[lo:hi], lw=0.7, color="k", ls="--", label="sum - 50,000")
    ax.axvline(s, color="grey", ls=":")
    ax.set_title(f"GOLDEN step at tick {s}: every pearl's change from the window start", fontsize=9)
    ax.legend(fontsize=6, ncol=6)
    # what happened to each pearl over the 500 ticks after vs the 500 before
    before = {SHORT[p]: round(mid[p].iloc[s] - mid[p].iloc[max(0, s - 500)]) for p in PE}
    after = {SHORT[p]: round(mid[p].iloc[min(len(mid) - 1, s + 500)] - mid[p].iloc[s]) for p in PE}
    print(f"  step {s}: 500 ticks before {before} | 500 ticks after {after} | sum dev at step {dev.iloc[s]:+.1f}")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "19_golden_steps.png"), dpi=100)
gt = TT[TT.symbol == "GOLDEN_PEARLS"]
for s in steps:
    pre = gt[(gt.t >= s - 300) & (gt.t < s)]
    print(f"  step {s}: GOLDEN trades in the 300 ticks before: {len(pre)} (buys {int((pre.side == 1).sum())}, sells {int((pre.side == -1).sum())});"
          f" typical per 300 ticks: {len(gt) / 100:.1f}")

# %% D. economic size: how often is the out-of-sample prediction bigger than the half-spread?
print("\nD. Day 0 (out-of-sample): how often |predicted 20-tick move| exceeds half the spread, and what then happened")
for p in PE:
    pred = preds[(p, 20)]
    y = mid[p].shift(-20) - mid[p]
    hs = spread[p] / 2
    sel = (day == 0) & y.notna() & (pred.abs() > hs)
    hit = np.sign(pred[sel]) == np.sign(y[sel])
    gain = (np.sign(pred[sel]) * y[sel] - hs[sel]).mean() if sel.any() else np.nan
    print(f"  {p:14s}: {sel.mean() * 100:5.1f}% of ticks; direction right {hit.mean() * 100 if sel.any() else float('nan'):5.1f}%;"
          f" avg move in predicted direction minus half-spread {gain:+.2f} coins")
