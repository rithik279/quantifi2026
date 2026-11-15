# %% [markdown]
# # Item 4: the lead-lag scan with a proper multiple-testing correction
# notebooks/weak/01_look.py kept a (predictor, target, horizon) if its correlation had the same sign on all
# three days. Under pure noise that happens with probability 2 x (1/2)^3 = 1/4, so a quarter of all tests
# pass by chance. Here every test gets a real p-value and Benjamini-Hochberg controls the false discovery
# rate:
#   - correlations use NON-overlapping windows (every k-th tick), so each day's n is honest;
#   - per-day correlations are combined with Fisher z + Stouffer into one two-sided p-value;
#   - BH at q = 5% across all tests.
# Run from repo root:  python notebooks/stats/03_leadlag_bh.py

# %%
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
import data  # noqa: E402
from stats_lib import benjamini_hochberg, fisher_p  # noqa: E402

OUT = os.path.join(data.ROOT, "outputs", "stats")
WEAK = ["JELLY", "PEANUT_BUTTER", "WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS", "GOLDEN_PEARLS",
        "FRUIT_BASKET", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN", "TELLURIUM"]
P = data.prices()
mid = data.wide(P)
day = mid.index.to_numpy() // 10_000 - 2
ALL = list(mid.columns)

rows = []
for k in (1, 5, 20, 100):
    past = mid.diff(k).to_numpy()
    fut = (mid.shift(-k) - mid).to_numpy()
    for jt, j in enumerate(ALL):
        if j not in WEAK:
            continue
        for it, i in enumerate(ALL):
            rs, ns, signs = [], [], []
            for d in (-2, -1, 0):
                idx = np.where(day == d)[0][k::k]  # non-overlapping windows within the day
                x, y = past[idx, it], fut[idx, jt]
                ok = ~(np.isnan(x) | np.isnan(y))
                r = np.corrcoef(x[ok], y[ok])[0, 1]
                rs.append(r); ns.append(ok.sum()); signs.append(np.sign(r))
            p, Z = fisher_p(rs, ns)
            rows.append(dict(target=j, predictor=i, k=k, r_d_2=rs[0], r_d_1=rs[1], r_d0=rs[2], n_per_day=ns[0],
                             same_sign_all_days=len(set(signs)) == 1, Z=Z, p=p))
L = pd.DataFrame(rows)
L["bh_5pct"] = benjamini_hochberg(L.p.to_numpy(), 0.05)
n = len(L)
print(f"{n} tests (11 weak targets x 26 predictors x 4 horizons)")
print(f"  pass the old 'same sign on all 3 days' filter: {L.same_sign_all_days.sum()} ({L.same_sign_all_days.mean():.0%}; "
      f"pure noise would give ~25%)")
print(f"  pass Benjamini-Hochberg at q = 5% (non-overlapping windows): {L.bh_5pct.sum()}")
print(f"  pass both: {(L.bh_5pct & L.same_sign_all_days).sum()}")
pd.set_option("display.width", 220)
print("\nSurvivors (BH 5% and same sign every day), strongest first:")
S = L[L.bh_5pct & L.same_sign_all_days].sort_values("p")
print(S[["target", "predictor", "k", "r_d_2", "r_d_1", "r_d0", "n_per_day", "Z", "p"]].round(4).to_string(index=False))
L.round(5).to_csv(os.path.join(OUT, "04_leadlag_bh.csv"), index=False)
own = S[S.target == S.predictor]
cross = S[S.target != S.predictor]
print(f"\n{len(own)} survivors are a product predicting itself (bid/ask bounce or momentum); {len(cross)} are cross-product.")
