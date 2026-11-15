# %% [markdown]
# # TELLURIUM spikes: do they come back? (Rithik's spike-fade / RSI idea)
# Idea: TELLURIUM makes sharp peaks in either direction. Measure the typical spike, fade it
# (sell an up-spike, buy a down-spike), exit when price is back near where the spike started, then
# wait for the next one. Like selling after a VIX spike, or RSI overbought/oversold.
#
# This script measures, using only information available at the time:
#   1. every spike: size, direction, and what happens next (continuation first? how much retraces?)
#   2. the average spike shape (all spikes aligned, scaled by size, flipped so "up" = spike direction)
#   3. RSI on the mid: what follows readings above 70/80/90 or below 30/20/10?
# Run from repo root:  python notebooks/weak/06_tellurium_spikes.py

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
m = data.wide(P, products=["TELLURIUM"])["TELLURIUM"].to_numpy()
day = np.arange(len(m)) // 10_000 - 2
N = len(m)

# %% 1. detect spikes: price moves more than J coins within L ticks (no overlap; 200-tick cooldown)
L, J, COOL = 5, 60, 200
events = []
t = L
while t < N:
    move = m[t] - m[t - L]
    if abs(move) >= J and day[t] == day[t - L]:
        # spike end = keep extending while the move continues in the same direction for up to 10 more ticks
        end = t
        for u in range(t + 1, min(t + 10, N)):
            if day[u] != day[t] or np.sign(m[u] - m[end]) != np.sign(move) or abs(m[u] - m[end]) < 1:
                break
            end = u
        pre = m[t - L]
        size = m[end] - pre
        rec = dict(day=int(day[t]), t=int(t), end=int(end), pre=pre, peak=m[end], size=size, dirn=int(np.sign(size)))
        for h in (20, 100, 200, 500, 1000, 2000):
            u = end + h
            if u < N and day[u] == day[end]:
                rec[f"ret_{h}"] = (m[end] - m[u]) / size  # fraction given back (1 = all the way to pre-spike level)
            else:
                rec[f"ret_{h}"] = np.nan
        horizon = [u for u in range(end + 1, min(end + 2000, N)) if day[u] == day[end]]
        path = (m[horizon] - m[end]) * np.sign(size) if horizon else np.array([0.0])
        rec["max_further"] = max(0.0, path.max())        # how much further it went in the spike's direction
        rec["max_giveback"] = max(0.0, -path.min()) / abs(size)
        back = np.where(-path >= abs(size))[0]
        half = np.where(-path >= 0.5 * abs(size))[0]
        rec["ticks_to_full"] = int(back[0]) + 1 if len(back) else np.nan
        rec["ticks_to_half"] = int(half[0]) + 1 if len(half) else np.nan
        events.append(rec)
        t = end + COOL
    else:
        t += 1
E = pd.DataFrame(events)
E.round(3).to_csv(os.path.join(OUT, "11_tellurium_spike_events.csv"), index=False)
print(f"{len(E)} spikes (>= {J} coins within {L} ticks): {E.groupby('day').size().to_dict()} by day, "
      f"{(E.dirn > 0).sum()} up / {(E.dirn < 0).sum()} down")
print("spike size |coins|: median %.0f, 75th pct %.0f" % (E['size'].abs().median(), E['size'].abs().quantile(0.75)))
cols = ["ret_20", "ret_100", "ret_200", "ret_500", "ret_1000", "ret_2000"]
print("\nFraction of the spike given back after h ticks (1.0 = back to the pre-spike level; negative = kept going):")
print("  all :", E[cols].median().round(2).to_dict(), "(median)")
print("  all :", E[cols].mean().round(2).to_dict(), "(mean)")
for d_ in (1, -1):
    print(f"  {'up  ' if d_ > 0 else 'down'}:", E[E.dirn == d_][cols].median().round(2).to_dict(), "(median)")
for dd in (-2, -1, 0):
    print(f"  day {dd}:", E[E.day == dd][cols].median().round(2).to_dict(), "(median)")
print("\nShare of spikes that get back to the pre-spike level within 2,000 ticks: %.0f%%" % (100 * E.ticks_to_full.notna().mean()))
print("Share that give back at least half within 2,000 ticks: %.0f%%" % (100 * E.ticks_to_half.notna().mean()))
print("Median ticks to half / full retrace (when it happens): %.0f / %.0f" % (E.ticks_to_half.median(), E.ticks_to_full.median()))
print("How far it kept going first (coins): median %.0f, 75th pct %.0f, max %.0f" % (
    E.max_further.median(), E.max_further.quantile(0.75), E.max_further.max()))

# %% 2. average spike shape
H = 2000
WIN = L + 50 + H
paths = []
for _, e in E.iterrows():
    s = int(e.t) - L - 50
    if s < 0 or s + WIN >= N or day[s] != day[s + WIN]:
        continue
    seg = (m[s:s + WIN] - e.pre) / e["size"]  # 0 = pre-spike level, 1 = peak, in the spike's direction
    paths.append(seg)
A = np.array(paths)
fig, ax = plt.subplots(figsize=(11, 4))
for row in A:
    ax.plot(np.arange(len(row)) - (L + 50), row, color="grey", lw=0.3, alpha=0.5)
ax.plot(np.arange(A.shape[1]) - (L + 50), np.median(A, axis=0), color="C3", lw=2, label="median spike")
ax.plot(np.arange(A.shape[1]) - (L + 50), np.percentile(A, 25, axis=0), color="C3", lw=0.8, ls="--", label="25th-75th pct")
ax.plot(np.arange(A.shape[1]) - (L + 50), np.percentile(A, 75, axis=0), color="C3", lw=0.8, ls="--")
ax.axhline(0, color="k", lw=0.6); ax.axhline(1, color="k", lw=0.4, ls=":")
ax.set_xlabel("ticks from spike start"); ax.set_ylabel("0 = pre-spike level, 1 = peak")
ax.set_title(f"TELLURIUM: every spike (n={len(A)}), scaled by its size and flipped to point up")
ax.set_ylim(-1.5, 2.5); ax.legend(fontsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "11_tellurium_spike_shape.png"), dpi=110)

# %% 3. RSI on the mid
def rsi(x, n):
    d = np.diff(x, prepend=x[0])
    up = pd.Series(np.maximum(d, 0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 * up / (up + dn).replace(0, np.nan)).to_numpy()


print("\nRSI: average move over the next h ticks after RSI crosses into a zone (per day; + = price went up)")
rows = []
for n in (14, 50, 200, 500):
    r = rsi(m, n)
    for lo, hi in ((30, 70), (20, 80), (10, 90)):
        for zone, cond in (("overbought", r > hi), ("oversold", r < lo)):
            entry = np.where(cond & ~np.r_[False, cond[:-1]])[0]  # first tick in the zone
            for h in (100, 500, 1000):
                for dd in (-2, -1, 0):
                    ok = [i for i in entry if i + h < N and day[i] == dd and day[i + h] == dd]
                    rows.append(dict(n=n, zone=zone, level=hi if zone == "overbought" else lo, h=h, day=dd,
                                     count=len(ok), move=np.mean([m[i + h] - m[i] for i in ok]) if ok else np.nan))
R = pd.DataFrame(rows)
piv = R.pivot_table(index=["n", "zone", "level", "h"], columns="day", values="move").round(1)
cnt = R.pivot_table(index=["n", "zone", "level", "h"], columns="day", values="count")
piv["entries/day"] = cnt.mean(axis=1).round(1)
piv["fade_works_all_days"] = [(row[-2] < 0 and row[-1] < 0 and row[0] < 0) if idx[1] == "overbought" else
                              (row[-2] > 0 and row[-1] > 0 and row[0] > 0) for idx, row in piv.iterrows()]
print(piv[piv.index.get_level_values("h") == 500].to_string())
R.round(2).to_csv(os.path.join(OUT, "12_tellurium_rsi_zones.csv"), index=False)
