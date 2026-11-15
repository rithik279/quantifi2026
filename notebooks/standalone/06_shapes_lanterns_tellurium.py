# %% [markdown]
# # Price shapes the summary stats missed (spotted on 01_price_paths.png)
# PAPER_LANTERNS: straight-line segments with kinks -> is the trend persistent once smoothed?
# TELLURIUM: sudden jumps that partly decay back -> how big, how often, how much reverts?
# Run from repo root:  python notebooks/standalone/06_shapes_lanterns_tellurium.py

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
mid = data.wide(P, products=["PAPER_LANTERNS", "TELLURIUM"])
day = mid.index // 10_000 - 2

# %% PAPER_LANTERNS: smoothed-trend persistence, per day
pl = mid["PAPER_LANTERNS"]
sm = pl.ewm(span=50).mean()  # remove the bid/ask bounce
print("PAPER_LANTERNS: corr(past smoothed change over h, next raw change over h), per day")
for h in (50, 200, 500, 1000):
    past = sm.diff(h)
    fut = pl.shift(-h) - pl
    cs = []
    for d in (-2, -1, 0):
        ok = (day == d) & past.notna() & fut.notna()
        cs.append(np.corrcoef(past[ok], fut[ok])[0, 1])
    print(f"  h={h:5d}: " + "  ".join(f"{c:+.2f}" for c in cs))

# slope magnitude in coins per tick over 500-tick windows
slope = sm.diff(500) / 500
print("  |slope| over 500 ticks: median %.3f coins/tick (=%.0f coins per 1,000 ticks)" % (slope.abs().median(), slope.abs().median() * 1000))
# How well does linear extrapolation of the smoothed series predict 20 ticks ahead vs the mid / EMA?
for name, pred in {"mid": pl, "ema50": sm, "ema50 + slope(200) x 25": sm + sm.diff(200) / 200 * 25}.items():
    print(f"  err predicting mid 20 ticks ahead with {name}: {(pl.shift(-20) - pred).abs().mean():.3f}")

# %% TELLURIUM: jumps
te = mid["TELLURIUM"]
dm = te.diff()
big = dm.abs() > 25
print(f"\nTELLURIUM: {big.sum()} one-tick jumps > 25 coins ({big.groupby(day).sum().to_dict()} by day)")
print("  jump size quantiles:", dm[big].abs().quantile([0.25, 0.5, 0.75, 0.95]).round(0).to_dict())
rows = []
for t in dm[big].index:
    j = dm.loc[t]
    after = {h: (te.shift(-h).loc[t] - te.loc[t]) * np.sign(j) for h in (5, 20, 100, 500)}
    before = (te.loc[t - 1] - te.shift(20).loc[t - 1]) * np.sign(j) if t - 21 in te.index else np.nan
    rows.append(dict(t=t, jump=j, before20=before, **{f"after{h}": v for h, v in after.items()}))
J = pd.DataFrame(rows)
print("  mean move in the jump's direction (negative = reverts):")
print(J[["jump", "before20", "after5", "after20", "after100", "after500"]].assign(jump=J.jump.abs()).mean().round(1).to_string())
J.round(1).to_csv(os.path.join(OUT, "13_tellurium_jumps.csv"), index=False)

# %% charts
fig, axes = plt.subplots(2, 1, figsize=(12, 6))
w = slice(0, 4_000)
axes[0].plot(pl.index[w], pl.iloc[w], lw=0.4, label="PAPER_LANTERNS mid")
axes[0].plot(sm.index[w], sm.iloc[w], lw=1.0, label="EMA 50")
axes[0].legend(); axes[0].set_title("PAPER_LANTERNS: piecewise-linear drift under bid/ask noise (first 4,000 ticks)")
k = J.t.iloc[len(J) // 2]
w2 = slice(max(0, k - 200), k + 600)
axes[1].plot(te.loc[w2].index, te.loc[w2].values, lw=0.6)
axes[1].axvline(k, color="red", lw=0.6, ls="--")
axes[1].set_title(f"TELLURIUM around a jump at tick {k}")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "14_lanterns_trend_tellurium_jump.png"), dpi=110)
