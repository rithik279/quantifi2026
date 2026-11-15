# %% [markdown]
# # TELLURIUM: market maker + glide overlay, vs the market maker alone
# The combined version (src/strategies/standalone.py, PARAMS["TELLURIUM"]["glide"]) market-makes as
# before, but after a jump it waits 20 ticks and, if the price is gliding, takes the full 40 units in
# the glide direction until the glide stalls; then it flattens and market making resumes.
# Compared per day, plus nearby settings and the stricter fill rule.
# Run from repo root:  python notebooks/weak/09_tellurium_combined.py

# %%
import copy
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
P_ = "TELLURIUM"
BASE = standalone.PARAMS[P_]
MM_ONLY = {k: v for k, v in BASE.items() if k != "glide"}


def with_glide(**kw):
    prm = copy.deepcopy(BASE)
    prm["glide"].update(kw)
    return prm


VARIANTS = {
    "A. market maker only (current submission)": (MM_ONLY, {}),
    "B. glide only (no market making)": ("glide_only", {}),
    "C. market maker + glide, flatten on exit (new default)": (BASE, {}),
    "D. market maker + glide, hand back to MM on exit": (with_glide(exit="mm"), {}),
    "E. C with wait W=40": (with_glide(W=40), {}),
    "F. C with stall window K=50": (with_glide(K=50), {}),
    "G. C with gmin=5": (with_glide(gmin=5), {}),
    "H. C with jump threshold J=100": (with_glide(J=100), {}),
    "stress A: only trades through our price fill": (MM_ONLY, dict(passive_mode="worse")),
    "stress C: only trades through our price fill": (BASE, dict(passive_mode="worse")),
    "D with wait W=40": (with_glide(exit="mm", W=40), {}),
    "D with stall window K=50": (with_glide(exit="mm", K=50), {}),
    "D with jump threshold J=100": (with_glide(exit="mm", J=100), {}),
    "stress D: only trades through our price fill": (with_glide(exit="mm"), dict(passive_mode="worse")),
    "stress C: 50% of eligible trades fill us": (BASE, dict(passive_fill_rate=0.5)),
    "stress D: 50% of eligible trades fill us": (with_glide(exit="mm"), dict(passive_fill_rate=0.5)),
}


def run(name):
    prm, stress = VARIANTS[name]
    if prm == "glide_only":
        fade = __import__("07_tellurium_fade_backtest")
        factory = lambda: fade.GlideTrader(J=60, W=20, gmin=15, K=20, flat=0.0, H=300)  # noqa: E731
    else:
        factory = lambda: standalone.Trader({P_: prm})  # noqa: E731
    res = bt.backtest(factory, (-2, -1, 0), [P_], record_every=0, **stress)
    return dict(variant=name, **{f"d{d.day}": d.pnl_by_product.get(P_, 0.0) for d in res.days},
                cancelled=sum(d.cancelled_for_limit.get(P_, 0) for d in res.days))


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(run, VARIANTS))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    df.to_csv(os.path.join(OUT, "15_tellurium_combined.csv"), index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70)
    print(df.round(0).to_string(index=False))
