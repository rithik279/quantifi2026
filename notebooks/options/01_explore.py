# %% [markdown]
# # Options: LYCHEE + VOUCHER_* first exploration
# Vouchers are European-style calls on LYCHEE (can't exercise; just trade them).
# Time to expiry = 8 days at the start of day -2, so TTE(day, ts) = 8 - (day + 2) - ts / 1e6 (in days).
# Scoring day 1 starts at TTE = 5 days.
# Run from repo root:  python notebooks/options/01_explore.py

# %%
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import data  # noqa: E402

OUT = os.path.join(data.ROOT, "outputs", "options")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)

STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = [f"VOUCHER_{k}" for k in STRIKES]
P = data.prices()
P = P[P["product"].isin(["LYCHEE"] + VOUCHERS)]
T = data.trades()
T = T[T["symbol"].isin(["LYCHEE"] + VOUCHERS)]
mid = data.wide(P)
S = mid["LYCHEE"]
t = mid.index.to_numpy()
day = t // 10_000 - 2
tte = 8 - (day + 2) - (t % 10_000) * 100 / 1e6  # days

# %% [markdown]
# ## 1. LYCHEE realised volatility

# %%
lr = np.log(S).diff()
per_day_vol = lr.groupby(day).std() * np.sqrt(10_000)
print("LYCHEE realised vol per day (std of daily log return implied by tick returns):\n", per_day_vol.round(5).to_string())
print("tick return autocorr lag1:", round(lr.autocorr(1), 3), " variance ratio(100):", round(np.log(S).diff(100).var() / (100 * lr.var()), 3))
# Robustness: vol from 100-tick returns avoids bid/ask bounce
vol100 = np.log(S).diff(100).groupby(day).std() * np.sqrt(100)
print("from 100-tick returns:\n", vol100.round(5).to_string())
print("LYCHEE open/close per day:", [(round(S[day == d].iloc[0]), round(S[day == d].iloc[-1])) for d in (-2, -1, 0)])

# %% [markdown]
# ## 2. Implied volatility per strike (Black-Scholes, r = 0, time in days, vol per sqrt(day))

# %%
def bs_call(S, K, T, sig):
    sqT = np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * sig ** 2 * T) / (sig * sqT)
    return S * norm.cdf(d1) - K * norm.cdf(d1 - sig * sqT)


def implied_vol(price, S, K, T, lo=1e-4, hi=0.2, iters=60):
    """Vectorised bisection. NaN where price is outside no-arbitrage bounds."""
    price, S, T = map(np.asarray, (price, S, T))
    intrinsic = np.maximum(S - K, 0)
    a, b = np.full(price.shape, lo), np.full(price.shape, hi)
    for _ in range(iters):
        m = (a + b) / 2
        too_high = bs_call(S, K, T, m) > price
        b = np.where(too_high, m, b)
        a = np.where(too_high, a, m)
    iv = (a + b) / 2
    bad = (price <= intrinsic + 1e-9) | (price >= S) | (iv > hi * 0.999) | (iv < lo * 1.001)
    return np.where(bad, np.nan, iv)


IV = pd.DataFrame({k: implied_vol(mid[f"VOUCHER_{k}"].to_numpy(), S.to_numpy(), k, tte) for k in STRIKES}, index=mid.index)
print("\nMedian implied vol by strike and day (per sqrt(day)):")
print(IV.groupby(day).median().round(5).to_string())
print("NaN share by strike:", IV.isna().mean().round(3).to_dict())

# %% [markdown]
# ## 3. The smile: IV vs moneyness m = log(K/S) / sqrt(T). Fit a quadratic per tick.

# %%
M = pd.DataFrame({k: np.log(k / S.to_numpy()) / np.sqrt(tte) for k in STRIKES}, index=mid.index)
mm, vv = M.to_numpy(), IV.to_numpy()
coefs = np.full((len(mm), 3), np.nan)
for i in range(len(mm)):
    ok = ~np.isnan(vv[i])
    if ok.sum() >= 5:
        coefs[i] = np.polyfit(mm[i, ok], vv[i, ok], 2)
C = pd.DataFrame(coefs, index=mid.index, columns=["a2", "a1", "a0"])
print("\nSmile fit coefficients (median per day): a0 = ATM vol")
print(C.groupby(day).median().round(5).to_string())
fitted = pd.DataFrame({k: C.a2 * M[k] ** 2 + C.a1 * M[k] + C.a0 for k in STRIKES})
resid_iv = IV - fitted

# convert IV residual to a price residual: market price - BS(fitted vol)
fair_px = pd.DataFrame({k: bs_call(S.to_numpy(), k, tte, fitted[k].to_numpy()) for k in STRIKES}, index=mid.index)
resid_px = pd.DataFrame({k: mid[f"VOUCHER_{k}"] - fair_px[k] for k in STRIKES})
print("\nPrice residual vs smile (market - fair), std and autocorr:")
rp = pd.DataFrame({"std": resid_px.std(), "mean": resid_px.mean(),
                   "ac1": [resid_px[k].autocorr(1) for k in STRIKES],
                   "ac20": [resid_px[k].autocorr(20) for k in STRIKES],
                   "ac100": [resid_px[k].autocorr(100) for k in STRIKES]})
print(rp.round(3).to_string())
rp.round(4).to_csv(os.path.join(OUT, "01_smile_residuals.csv"))

# Does the residual predict the voucher's next move (relative to what the smile says)?
rows = []
for k in STRIKES:
    v = mid[f"VOUCHER_{k}"]
    for h in (1, 10, 50):
        fwd = v.shift(-h) - v
        fwd_fair = fair_px[k].shift(-h) - fair_px[k]
        ok = fwd.notna() & resid_px[k].notna()
        rows.append(dict(strike=k, h=h,
                         slope_raw=np.polyfit(resid_px[k][ok], fwd[ok], 1)[0],
                         slope_rel=np.polyfit(resid_px[k][ok], (fwd - fwd_fair)[ok].fillna(0), 1)[0]))
pr = pd.DataFrame(rows).pivot(index="strike", columns="h", values="slope_raw")
print("\nSlope of future voucher price change on current smile residual (-1 = residual fully closes):\n", pr.round(3).to_string())

# %% [markdown]
# ## 4. Is IV high vs realised? (vol risk premium)

# %%
atm = C.a0
print("\nATM IV mean per day vs realised (per sqrt(day)):")
print(pd.DataFrame({"atm_iv": atm.groupby(day).mean(), "realised_tick": per_day_vol, "realised_100": vol100}).round(5).to_string())

# %% [markdown]
# ## 5. Voucher book and trades

# %%
rows = []
for p in ["LYCHEE"] + VOUCHERS:
    g = P[P["product"] == p]; tr = T[T["symbol"] == p]
    rows.append(dict(product=p, mid=g.mid_price.mean(), spread_med=g.spread.median(), trades_per_day=len(tr) / 3,
                     avg_qty=tr.quantity.mean(), top_vol=g.bid_volume_1.median()))
print("\n", pd.DataFrame(rows).set_index("product").round(2).to_string())

# delta of each voucher (for hedging) at median conditions
sig = np.nanmedian(C.a0)
for k in STRIKES:
    d1 = (np.log(S.median() / k) + 0.5 * sig ** 2 * 5) / (sig * np.sqrt(5))
    print(f"delta {k}: {norm.cdf(d1):.3f}", end="  ")
print()

# %% charts
fig, ax = plt.subplots(figsize=(7, 4))
for d, c in zip((-2, -1, 0), ("C0", "C1", "C2")):
    sel = (day == d) & (np.arange(len(day)) % 500 == 0)
    ax.scatter(M[sel].to_numpy().ravel(), IV[sel].to_numpy().ravel(), s=4, color=c, label=f"day {d}")
ax.set_xlabel("moneyness log(K/S)/sqrt(T)"); ax.set_ylabel("implied vol (per sqrt(day))"); ax.legend()
ax.set_title("Volatility smile (snapshots every 500 ticks)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "02_smile.png"), dpi=110)

fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
axes[0].plot(S.index, S, lw=0.6); axes[0].set_title("LYCHEE mid")
axes[1].plot(C.index, C.a0.rolling(50).median(), lw=0.6, label="ATM IV (smile a0)")
axes[1].axhline(per_day_vol.mean(), color="red", lw=0.6, ls="--", label="realised (mean)")
axes[1].legend(); axes[1].set_title("ATM implied vol vs realised")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "03_lychee_and_atm_iv.png"), dpi=110)

fig, ax = plt.subplots(figsize=(12, 3))
for k in (7300, 7500, 7750):
    ax.plot(resid_px.index[:3000], resid_px[k].iloc[:3000], lw=0.6, label=f"{k}")
ax.axhline(0, color="k", lw=0.5); ax.legend(); ax.set_title("Price residual vs smile (first 3,000 ticks of day -2)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "04_smile_residuals.png"), dpi=110)

C.to_csv(os.path.join(data.ROOT, "data", "processed", "options_smile_coefs.csv"))
print("charts written to", OUT)
