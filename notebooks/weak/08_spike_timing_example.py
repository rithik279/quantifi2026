# %% [markdown]
# # When exactly do the spike strategies act? (answering "are we acting after the spike is over?")
# Runs three of the prototypes from 07 on day 0 and prints, for each spike: the tick the jump first
# shows in the book, the tick our code detected it, and the ticks/prices where it entered and exited.
# Then charts four spikes with those marks.
# Run from repo root:  python notebooks/weak/08_spike_timing_example.py

# %%
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import backtester as bt  # noqa: E402
fade = __import__("07_tellurium_fade_backtest")  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
DAY = 0
data = bt.get_day(DAY, [fade.PROD])
mid = data.mids[fade.PROD]
ts = np.array(data.timestamps) // 100

VARIANTS = {
    "fade at once (naive, D=0)": dict(mode="naive", J=60, D=0, f=1.0, H=500),
    "fade after 100 ticks (naive, D=100)": dict(mode="naive", J=60, D=100, f=0.5, H=500),
    "confirmed fade (c=0.2)": dict(mode="confirmed", J=60, c=0.2, f=0.8, H=1000),
}


class Logged(fade.SpikeFade):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.log = []

    def run(self, state):
        had_spike, had_trade = self.spike is not None, self.trade is not None
        out = super().run(state)
        t = state.timestamp // 100
        if not had_spike and self.spike is not None:
            self.log.append(dict(event="detected", t=t, mid=self.hist[-1], pre=self.spike["pre"]))
        if not had_trade and self.trade is not None:
            self.log.append(dict(event="enter " + ("short" if self.trade["side"] < 0 else "long"), t=t, mid=self.hist[-1]))
        if had_trade and self.trade is None:
            self.log.append(dict(event="exit", t=t, mid=self.hist[-1]))
        return out


# the actual one-tick jumps (from the price data, for reference)
jumps = [int(i) for i in np.where(np.abs(np.diff(mid)) >= 60)[0] + 1]
print(f"day {DAY}: one-tick jumps of >= 60 coins at ticks {jumps}")
print(f"  e.g. tick {jumps[0]}: mid {mid[jumps[0] - 1]:.1f} -> {mid[jumps[0]]:.1f} in a single tick\n")

logs = {}
for name, kw in VARIANTS.items():
    tr = Logged(**kw)
    tr.set_day = lambda d: None
    bt.run_day(tr, data, record_every=0)
    L = pd.DataFrame(tr.log)
    logs[name] = L
    print(f"=== {name} ===")
    print(L.head(12).round(1).to_string(index=False))
    print()

# chart four spikes with the marks
fig, axes = plt.subplots(2, 2, figsize=(13, 7))
for ax, j in zip(axes.ravel(), jumps[:4]):
    lo, hi = max(0, j - 60), min(len(mid), j + 700)
    ax.plot(np.arange(lo, hi), mid[lo:hi], color="k", lw=0.8)
    ax.axvline(j, color="grey", ls=":", lw=1)
    for (name, L), col in zip(logs.items(), ("C0", "C1", "C2")):
        sub = L[(L.t >= lo) & (L.t < hi)]
        for _, r in sub.iterrows():
            mk = {"detected": "o", "exit": "x"}.get(r.event, "v" if "short" in r.event else "^")
            ax.scatter(r.t, r.mid, marker=mk, s=60, color=col, zorder=3,
                       label=f"{name}: {r.event}" if ax is axes[0][0] else None)
    ax.set_title(f"spike at tick {j} (day {DAY})", fontsize=9)
axes[0][0].legend(fontsize=6, loc="best")
fig.suptitle("When each version acts: o = detected, v/^ = enter short/long, x = exit (dotted line = the jump tick)", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "14_spike_timing_examples.png"), dpi=105)
