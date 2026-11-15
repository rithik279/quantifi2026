# %% [markdown]
# # Basket: does the premium revert, trend, or neither? Checked day by day.
# premium = FRUIT_BASKET - (2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN)
# Signal = premium minus its EMA (span W). Positive corr with the future premium change = momentum,
# negative = mean reversion. A signal is only worth trading if the sign holds on every day.
# Run from repo root:  python notebooks/basket/02_premium_signals.py

# %%
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import data  # noqa: E402

OUT = os.path.join(data.ROOT, "outputs", "basket")
FRUITS = ["DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"]
P = data.prices()
mid = data.wide(P, products=["FRUIT_BASKET"] + FRUITS)
prem = mid["FRUIT_BASKET"] - mid[FRUITS] @ np.array([2, 3, 1])
day = prem.index // 10_000 - 2

rows = []
for W in (200, 500, 1000, 2000, 5000):
    sig = prem - prem.ewm(span=W).mean()
    for H in (50, 200, 1000):
        fwd = prem.shift(-H) - prem
        for d in (-2, -1, 0):
            ok = (day == d) & fwd.notna() & (np.arange(len(prem)) % 10_000 > W)  # skip EMA warm-up
            c = np.corrcoef(sig[ok], fwd[ok])[0, 1]
            rows.append(dict(W=W, H=H, day=d, corr=c))
tab = pd.DataFrame(rows).pivot_table(index=["W", "H"], columns="day", values="corr")
tab["same_sign_all_days"] = (np.sign(tab[[-2, -1, 0]]).nunique(axis=1) == 1)
print("corr(premium - EMA_W, premium change over next H ticks), per day:\n", tab.round(3).to_string())
tab.round(4).to_csv(os.path.join(OUT, "03_premium_signal_by_day.csv"))

# Fixed anchor: does the premium get pulled toward 0 (or toward its 3-day mean)?
for anchor in (0, prem.mean()):
    for H in (1000, 3000):
        fwd = prem.shift(-H) - prem
        ok = fwd.notna()
        b = np.polyfit((prem - anchor)[ok], fwd[ok], 1)[0]
        print(f"anchor {anchor:7.1f}, H={H}: slope of future change on (premium - anchor) = {b:.3f}")

# How big are premium moves vs the cost of trading the full hedge (~15 coins one way)?
for H in (100, 1000):
    print(f"|premium change| over {H} ticks: median {prem.diff(H).abs().median():.1f}")
