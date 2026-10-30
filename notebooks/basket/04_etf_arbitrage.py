# %% [markdown]
# # Basket as ETF-vs-NAV arbitrage: why the gap doesn't close
# In a real ETF, authorised dealers can create or redeem baskets (swap fruits for baskets and back), so
# any gap between the ETF and its NAV is closed by arbitrage. Here we can't convert anything: we can
# only hold the basket against the fruits and wait. So:
#   1. At executable prices (sell at the bid, buy at the ask), how big is the "arbitrage" gap?
#   2. Who moves the premium: the basket on its own, or the fruits?
#   3. Are the 2/3/1 weights stable through the day, or do they drift (which would make the premium drift)?
#   4. Does anything else in the market move with the premium?
#   5. If we enter when the gap is large, does it close? (per day, at executable prices)
# Run from repo root:  python notebooks/basket/04_etf_arbitrage.py

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

OUT = os.path.join(data.ROOT, "outputs", "basket")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 220)
B, FR, W = "FRUIT_BASKET", ["DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"], np.array([2, 3, 1])
P = data.prices()
mid = data.wide(P)
bid, ask = data.wide(P, "bid_price_1"), data.wide(P, "ask_price_1")
day = pd.Series(mid.index // 10_000 - 2, index=mid.index)

nav = mid[FR] @ W
prem = mid[B] - nav
# 1. executable gaps: sell basket at its bid and buy the fruits at their asks (and the reverse)
sell_gap = bid[B] - ask[FR] @ W     # > 0: basket rich even after paying every spread
buy_gap = bid[FR] @ W - ask[B]      # > 0: basket cheap even after paying every spread
cross_cost = (mid[B] - bid[B]) + (ask[FR] - mid[FR]) @ W
print(f"1. Crossing all four books once costs {cross_cost.mean():.1f} coins per basket (mid to executable).")
print("   Premium (mid) per day: mean / std / min / max")
print(prem.groupby(day).agg(["mean", "std", "min", "max"]).round(0).to_string())
print(f"   Share of ticks where selling the basket and buying the fruits is 'profitable' at executable prices"
      f" (sell_gap > 0): {(sell_gap > 0).mean():.0%};  the reverse (buy_gap > 0): {(buy_gap > 0).mean():.0%}")
print("   ...but with no create/redeem, 'profitable' only means 'the premium is positive right now'.\n")

# 2. who moves the premium?
for h in (1, 100, 1000):
    db, dn, dp = mid[B].diff(h), nav.diff(h), prem.diff(h)
    vb, vn, cov = db.var(), dn.var(), np.cov(db.dropna(), dn.dropna())[0, 1]
    print(f"2. h={h:5d}: var(premium change) = var(basket) {vb:9.0f} + var(NAV) {vn:9.0f} - 2cov {2 * cov:9.0f}"
          f"  -> basket-only noise share {(vb - cov) / dp.var():.0%}, NAV-only share {(vn - cov) / dp.var():.0%}")
print("   (shares above 100% / below 0 mean the legs offset each other)\n")

# 3. rolling weights (10-tick changes, 2,000-tick windows)
rows = []
d10 = mid[[B] + FR].diff(10)
for start in range(0, len(mid) - 2000, 1000):
    w = d10.iloc[start:start + 2000].dropna()
    X = np.column_stack([w[FR].to_numpy(), np.ones(len(w))])
    coef, *_ = np.linalg.lstsq(X, w[B].to_numpy(), rcond=None)
    rows.append(dict(start_tick=start, D=coef[0], G=coef[1], M=coef[2]))
RW = pd.DataFrame(rows)
print("3. Rolling weights (10-tick changes, 2,000-tick windows):")
print(RW[["D", "G", "M"]].describe().loc[["mean", "std", "min", "max"]].round(2).to_string())
RW.round(3).to_csv(os.path.join(OUT, "06_rolling_weights.csv"), index=False)

# 4. does anything else move with the premium? (100-tick changes, per day)
print("\n4. Correlation of 100-tick premium changes with each product's 100-tick changes (top 6 by |corr|, all days):")
dp = prem.diff(100)
rows = []
for p in mid.columns:
    if p in [B] + FR:
        continue
    cs = [np.corrcoef(dp[(day == d) & dp.notna()], mid[p].diff(100)[(day == d) & dp.notna()])[0, 1] for d in (-2, -1, 0)]
    rows.append(dict(product=p, d_2=cs[0], d_1=cs[1], d0=cs[2], mean=np.mean(cs)))
C = pd.DataFrame(rows).sort_values("mean", key=abs, ascending=False)
print(C.head(6).round(3).to_string(index=False))

# 5. enter when the premium is far from 0, at executable prices; how often does it come back within H ticks?
print("\n5. If we sell the basket / buy fruits when the premium is >= X above 0 (or the reverse), "
      "what happens over the next H ticks? (mid premium, per day)")
rows = []
for X in (200, 400, 600):
    for H in (500, 2000):
        for d in (-2, -1, 0):
            s = prem[day == d].to_numpy()
            entries = [i for i in range(len(s) - H) if abs(s[i]) >= X and (i == 0 or abs(s[i - 1]) < X)]
            if not entries:
                rows.append(dict(X=X, H=H, day=d, entries=0)); continue
            gain = [np.sign(s[i]) * (s[i] - s[i + H]) - cross_cost.mean() * 2 for i in entries]
            rows.append(dict(X=X, H=H, day=d, entries=len(entries), mean_gain=np.mean(gain), share_positive=np.mean(np.array(gain) > 0)))
R = pd.DataFrame(rows)
print(R.pivot_table(index=["X", "H"], columns="day", values=["entries", "mean_gain"]).round(0).to_string())

# chart
fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
axes[0].plot(mid.index, prem, lw=0.5, label="premium at mids")
axes[0].plot(mid.index, sell_gap, lw=0.4, alpha=0.6, label="sell basket / buy fruits at executable prices")
axes[0].plot(mid.index, -buy_gap, lw=0.4, alpha=0.6, label="minus (buy basket / sell fruits)")
axes[0].axhline(0, color="k", lw=0.5); axes[0].legend(fontsize=7); axes[0].set_title("Basket premium vs NAV (2D + 3G + 1M)")
for c in ("D", "G", "M"):
    axes[1].plot(RW.start_tick + 1000, RW[c], marker="o", ms=3, label=c)
axes[1].axhline(2, color="C0", lw=0.4, ls=":"); axes[1].axhline(3, color="C1", lw=0.4, ls=":"); axes[1].axhline(1, color="C2", lw=0.4, ls=":")
axes[1].legend(fontsize=7); axes[1].set_title("Rolling weights (2,000-tick windows): do 2/3/1 hold?")
axes[2].plot(mid.index, mid[B] - mid[B].iloc[0], lw=0.5, label="basket (change)")
axes[2].plot(mid.index, nav - nav.iloc[0], lw=0.5, label="NAV (change)")
axes[2].legend(fontsize=7); axes[2].set_title("Basket and NAV, change from start")
for ax in axes:
    for b in (10_000, 20_000):
        ax.axvline(b, color="grey", lw=0.5, ls="--")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "07_etf_arbitrage.png"), dpi=100)
