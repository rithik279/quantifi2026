# %% [markdown]
# # PEANUT_BUTTER & JELLY as a pair
# Finding (03_pbj_hints.py): their price changes correlate +0.6 tick by tick and up to +0.85 over
# 1,000 ticks, on every day, and nothing else correlates with either. So model
#     JELLY ~ beta x PEANUT_BUTTER + spread
# and ask: is the spread more predictable (mean-reverting) than either leg? If so, either
#   (a) trade the spread (long one leg, short the other), or
#   (b) use PB to sharpen JELLY's fair value, then market-make JELLY's wide (11-coin) spread and
#       hedge the inventory with PB, whose spread is cheap relative to its moves.
# Run from repo root:  python notebooks/weak/04_pbj_pair.py

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
P = data.prices()
mid = data.wide(P, products=["PEANUT_BUTTER", "JELLY"])
pb, j = mid["PEANUT_BUTTER"], mid["JELLY"]
day = pd.Series(mid.index // 10_000 - 2, index=mid.index)

# %% hedge ratio from changes (levels would be spurious), per day and pooled
print("beta (JELLY change on PB change):")
for h in (1, 10, 100):
    bs = []
    for d in (-2, -1, 0):
        s = day == d
        x, y = pb.diff(h)[s].dropna(), j.diff(h)[s].dropna()
        bs.append(np.polyfit(x, y, 1)[0])
    print(f"  h={h:4d}: " + "  ".join(f"{b:.3f}" for b in bs))
x, y = pb.diff(10).dropna(), j.diff(10).dropna()
beta = np.polyfit(x, y, 1)[0]
print(f"pooled beta (10-tick changes): {beta:.3f}")

# %% the spread
S = j - beta * pb
print("\nSpread S = JELLY - beta x PB, per day:")
for d in (-2, -1, 0):
    s = S[day == d]
    dd = s - s.mean()
    phi = np.dot(dd[1:], dd[:-1]) / np.dot(dd[:-1], dd[:-1])
    print(f"  day {d}: mean {s.mean():8.1f}  std {s.std():6.1f}  half-life {np.log(0.5) / np.log(phi):7.0f} ticks"
          f"   | JELLY std {j[day == d].std():6.1f}, PB std {pb[day == d].std():6.1f}")
for h in (10, 100, 1000):
    print(f"  variance ratio at h={h}: S {S.diff(h).var() / (h * S.diff().var()):.3f}   JELLY {j.diff(h).var() / (h * j.diff().var()):.3f}   PB {pb.diff(h).var() / (h * pb.diff().var()):.3f}")

# Does the spread's deviation from its recent average predict which leg moves? (per day)
print("\nSlope of each leg's next-h change on (S - EMA_W(S)): who closes the gap? (per day)")
for W in (50, 200, 1000):
    dev = S - S.ewm(span=W).mean()
    for h in (20, 100, 500):
        out = []
        for leg, s_ in (("JELLY", j), ("PB", pb)):
            sl = []
            for d in (-2, -1, 0):
                sel = (day == d) & s_.shift(-h).notna() & (np.arange(len(S)) % 10_000 > W)
                sl.append(np.polyfit(dev[sel], (s_.shift(-h) - s_)[sel], 1)[0])
            out.append(f"{leg} " + " ".join(f"{v:+.2f}" for v in sl))
        print(f"  W={W:4d} h={h:3d}:  " + "   |   ".join(out))

# %% does PB sharpen JELLY's fair value? (predict JELLY 20 ticks ahead)
print("\nMean abs error predicting JELLY 20 ticks ahead, per day:")
fut = j.shift(-20)
for W in (50, 200):
    dev = S - S.ewm(span=W).mean()
    for c in (0.0, 0.25, 0.5, 1.0):
        pred = j - c * dev
        errs = [(fut - pred).abs()[day == d].mean() for d in (-2, -1, 0)]
        print(f"  W={W:3d}, JELLY mid - {c:.2f} x spread deviation: " + "  ".join(f"{e:.3f}" for e in errs))

# %% hedging value: how much does holding -beta PB per JELLY cut the risk?
for h in (100, 1000):
    print(f"\n{h}-tick std: JELLY alone {j.diff(h).std():.1f}  vs  JELLY - beta x PB {S.diff(h).std():.1f}"
          f"  ({1 - S.diff(h).std() / j.diff(h).std():.0%} less risk)")

fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
axes[0].plot(mid.index, j, lw=0.5, label="JELLY")
axes[0].plot(mid.index, beta * pb + (j - beta * pb).mean(), lw=0.5, label=f"{beta:.2f} x PEANUT_BUTTER (shifted)")
axes[0].legend(fontsize=7); axes[0].set_title("JELLY vs beta x PEANUT_BUTTER")
axes[1].plot(mid.index, S, lw=0.5); axes[1].set_title("Spread S = JELLY - beta x PB")
for ax in axes:
    for b in (10_000, 20_000):
        ax.axvline(b, color="grey", lw=0.5, ls="--")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "09_pbj_spread.png"), dpi=100)
