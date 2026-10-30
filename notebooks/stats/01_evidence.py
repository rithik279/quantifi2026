# %% [markdown]
# # Items 1 and 2: how much independent evidence is behind each structural fact?
# 1. Effective sample size N_eff = T (1 - rho) / (1 + rho) for each fact's underlying series, plus the
#    count of independent episodes (days, jumps, slides) for the facts that rest on events.
# 2. Honest t-statistics for the "X predicts Y over h ticks" claims. Each was measured on per-tick,
#    overlapping h-tick windows, which share up to h-1 ticks, so a naive t is inflated by roughly sqrt(h).
#    For each claim: naive t, Newey-West t with lag h-1 (lag set by the construction, not the data), and
#    the plain t on non-overlapping windows (every h-th tick).
# Run from repo root:  python notebooks/stats/01_evidence.py

# %%
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))
import data  # noqa: E402
from stats_lib import ar1, n_eff, nonoverlap_ols, ols_hac  # noqa: E402

OUT = os.path.join(data.ROOT, "outputs", "stats")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 230); pd.set_option("display.max_colwidth", 60)

P = data.prices()
mid = data.wide(P)
day = mid.index.to_numpy() // 10_000 - 2
T = len(mid)
PE = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
FR, W = ["DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"], np.array([2, 3, 1])
sumdev = mid[PE].sum(axis=1) - 50_000
prem = mid["FRUIT_BASKET"] - mid[FR] @ W
pbj_gap = mid["JELLY"] - 0.412 * mid["PEANUT_BUTTER"]
toffee_dev = mid["TOFFEE_CAKE"] - 5_000
lant_slope = mid["PAPER_LANTERNS"].ewm(span=50).mean().diff(200)  # smoothed 200-tick slope

# voucher residual vs its own slow-IV fair value: approximate with price minus a 1,000-tick EMA of
# (price - BS-free proxy) is overkill; use the smile residuals saved by the options workstream if present
res_path = os.path.join(data.ROOT, "outputs", "options", "01_smile_residuals.csv")

# %% 1. effective sample size
rows = []


def add(fact, series, note, episodes=None):
    s = pd.Series(series).dropna()
    rho = ar1(s)
    rows.append(dict(fact=fact, T=len(s), rho_lag1=rho, half_life_ticks=(np.log(0.5) / np.log(rho)) if 0 < rho < 1 else np.nan,
                     N_eff=n_eff(len(s), rho), independent_episodes=episodes, note=note))


add("TOFFEE_CAKE deviation from 5,000", toffee_dev, "reversion is well supported; the LEVEL 5,000 itself is one value seen on 3 days", "3 days at one level")
add("Pearl sum deviation from 50,000", sumdev, "PINK's signal", "3 days")
add("Basket premium (basket - 2D - 3G - 1M)", prem, "'pulled toward 0' rests on ~1 cycle", "~1 slow cycle")
add("PB & J gap (JELLY - 0.41 PB)", pbj_gap, "slow wander; hedge use only", None)
add("PAPER_LANTERNS smoothed 200-tick slope", lant_slope, "trend persistence; units are trend segments", None)
# count trend segments: sign changes of the smoothed slope (sampled every 200 ticks to avoid flicker)
seg = np.sign(lant_slope.iloc[::200].dropna().to_numpy())
rows[-1]["independent_episodes"] = f"{int((seg[1:] != seg[:-1]).sum()) + 1} trend segments"
tel = mid["TELLURIUM"].to_numpy()
n_jumps = int((np.abs(tel[5:] - tel[:-5]) >= 60).sum())  # rough count of jump ticks
rows.append(dict(fact="TELLURIUM jumps (>= 60 coins in 5 ticks)", T=T, rho_lag1=np.nan, half_life_ticks=np.nan, N_eff=np.nan,
                 independent_episodes="28 spikes (event study)", note="glide overlay rests on these"))
rows.append(dict(fact="GOLDEN_PEARLS slides between plateaus", T=T, rho_lag1=np.nan, half_life_ticks=np.nan, N_eff=np.nan,
                 independent_episodes="3 slides", note="slide overlay rests on these"))
if os.path.exists(res_path):
    rows.append(dict(fact="Voucher price vs smile (per strike)", T=T, rho_lag1=0.99, half_life_ticks=np.log(0.5) / np.log(0.99),
                     N_eff=n_eff(T, 0.99), independent_episodes="10 strikes x ~150", note="lag-1 autocorr ~0.99 from options/01"))
E = pd.DataFrame(rows)
print("1. Effective sample size of each structural fact (T = 30,000 ticks)")
print(E.round(4).to_string(index=False))
E.round(4).to_csv(os.path.join(OUT, "01_effective_sample_size.csv"), index=False)

# %% 2. honest t-stats for the "predicts" claims
claims = []


def claim(name, x, y, h):
    r = ols_hac(x, y, h - 1)
    # non-overlapping: average over a few staggered starts to use more of the data
    starts = np.linspace(0, h - 1, min(h, 5)).astype(int)
    no = [nonoverlap_ols(x, y, h, s) for s in starts]
    claims.append(dict(claim=name, h=h, slope=r["slope"], t_naive=r["t_naive"], t_newey_west=r["t_hac"],
                       t_nonoverlap_mean=np.nanmean([z["t"] for z in no]), n_nonoverlap=no[0]["n"],
                       inflation=r["t_naive"] / r["t_hac"] if r["t_hac"] else np.nan))


for h in (20, 50, 200):
    claim("PINK next-h change on (sum - 50,000)", sumdev.to_numpy(), (mid["PINK_PEARLS"].shift(-h) - mid["PINK_PEARLS"]).to_numpy(), h)
for h in (100, 1000):
    claim("TOFFEE next-h change on (mid - 5,000)", toffee_dev.to_numpy(), (mid["TOFFEE_CAKE"].shift(-h) - mid["TOFFEE_CAKE"]).to_numpy(), h)
sm = mid["PAPER_LANTERNS"].ewm(span=50).mean()
for h in (50, 1000):
    claim("LANTERNS next-h change on past smoothed h change", sm.diff(h).to_numpy(), (mid["PAPER_LANTERNS"].shift(-h) - mid["PAPER_LANTERNS"]).to_numpy(), h)
claim("Basket premium next-3000 change on (premium - 0)", prem.to_numpy(), (prem.shift(-3000) - prem).to_numpy(), 3000)
claim("BLUE next-5 change on its last-5 change", mid["BLUE_PEARLS"].diff(5).to_numpy(), (mid["BLUE_PEARLS"].shift(-5) - mid["BLUE_PEARLS"]).to_numpy(), 5)
for h in (100, 500):
    claim("JELLY next-h change on (JELLY - 0.41 PB gap - its 1,000-EMA)", (pbj_gap - pbj_gap.ewm(span=1000).mean()).to_numpy(),
          (mid["JELLY"].shift(-h) - mid["JELLY"]).to_numpy(), h)
C = pd.DataFrame(claims)
print("\n2. 'Predicts' claims: naive t (overlapping windows, iid) vs Newey-West t (lag h-1) vs non-overlapping t")
print(C.round(3).to_string(index=False))
C.round(4).to_csv(os.path.join(OUT, "02_honest_tstats.csv"), index=False)

# %% TELLURIUM glide as an event study: does the glide direction seen 20 ticks after a jump persist?
jt = []
t = 5
while t < T - 300:
    if abs(tel[t] - tel[t - 5]) >= 60 and day[t] == day[t + 300]:
        g = tel[t + 20] - tel[t]
        if abs(g) >= 15:
            jt.append(np.sign(g) * (tel[t + 120] - tel[t + 20]))
        t += 200
    else:
        t += 1
jt = np.array(jt)
from scipy.stats import binomtest  # noqa: E402
print(f"\nTELLURIUM glide events: n={len(jt)}, mean move in the glide direction over the next 100 ticks "
      f"{jt.mean():+.1f} coins, t = {jt.mean() / (jt.std(ddof=1) / np.sqrt(len(jt))):.2f}, "
      f"positive {np.mean(jt > 0):.0%}, sign-test p = {binomtest(int((jt > 0).sum()), len(jt), 0.5, 'greater').pvalue:.3f}")
pd.DataFrame({"glide_followthrough_100": jt}).to_csv(os.path.join(OUT, "02_tellurium_glide_events.csv"), index=False)
