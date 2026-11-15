# %% [markdown]
# # Item 6: fragility band: which differences between settings are real?
# 1. Noise band: rerun each strategy's chosen setting with a random 5% of its passive fills dropped
#    (5 seeds). The spread of those totals is how much PnL moves for reasons that shouldn't matter.
# 2. For each chosen setting vs its nearest alternatives: total difference, and a paired test on the same
#    30 blocks (Newey-West t of the per-block difference, share of blocks where the chosen one is better).
# Verdict per comparison:
#   "real"  : |difference| > 2 x the noise band AND paired |t| >= 2
#   "noise with an ordering" otherwise: the chosen setting may be slightly better or worse, but the data
#   can't tell, so the choice should rest on other grounds (plateau, simplicity, risk).
# Run from repo root:  python notebooks/stats/05_fragility_band.py

# %%
import copy
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402
import pearls  # noqa: E402
import standalone  # noqa: E402
from stats_lib import hac_mean_t  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "stats")
BLOCK_TS = 100_000
OPT = [options.UNDERLYING] + list(options.VOUCHERS)

# unit -> (group, book, scored products, base params of the unit)
UNITS = {
    "options": ("options", OPT, OPT, {}),
    "PINK": ("pearls", pearls.PEARLS, ["PINK_PEARLS"], copy.deepcopy(pearls.PARAMS["PINK_PEARLS"])),
    "TELLURIUM": ("standalone", ["TELLURIUM"], ["TELLURIUM"], copy.deepcopy(standalone.PARAMS["TELLURIUM"])),
    "LANTERNS": ("standalone", ["PAPER_LANTERNS"], ["PAPER_LANTERNS"], copy.deepcopy(standalone.PARAMS["PAPER_LANTERNS"])),
    "TOFFEE": ("standalone", ["TOFFEE_CAKE"], ["TOFFEE_CAKE"], copy.deepcopy(standalone.PARAMS["TOFFEE_CAKE"])),
}
ALTS = {
    "options": [("hedge_band", 120), ("hedge_band", 30), ("hedge_band", 240), ("iv_span", 500), ("iv_span", 2000),
                ("take_k", 0.6), ("take_k", 1.0)],
    "PINK": [("k", 0.25), ("k", 0.75), ("k", 1.0)],
    "TELLURIUM": [("soft_cap", 10), ("soft_cap", 20), ("glide.W", 40), ("glide.exit", "mm")],
    "LANTERNS": [("lead", 50), ("lead", 200)],
    "TOFFEE": [("take_edge", 5), ("take_edge", 10)],
}
UNIT_PRODUCT = {"PINK": "PINK_PEARLS", "TELLURIUM": "TELLURIUM", "LANTERNS": "PAPER_LANTERNS", "TOFFEE": "TOFFEE_CAKE"}


def params_for(unit, change):
    group, book, score, base = UNITS[unit]
    prm = copy.deepcopy(base)
    if change is not None:
        key, val = change
        if "." in key:
            a, b = key.split(".")
            prm[a][b] = val
        else:
            prm[key] = val
    return prm


def run(job):
    unit, change, stress = job
    group, book, score, _ = UNITS[unit]
    prm = params_for(unit, change)
    if group == "options":
        f = lambda: options.Trader(prm)  # noqa: E731
    elif group == "pearls":
        f = lambda: pearls.Trader({UNIT_PRODUCT[unit]: prm})  # noqa: E731
    else:
        f = lambda: standalone.Trader({UNIT_PRODUCT[unit]: prm})  # noqa: E731
    res = bt.backtest(f, (-2, -1, 0), book, record_every=100, **stress)
    blocks = []
    for d in res.days:
        c = d.pnl_curve.drop(columns="TOTAL", errors="ignore")
        ends = sorted(set([ts for ts in c.index if ts % BLOCK_TS == 0 and ts > 0] + [c.index[-1]]))
        v = c[[p for p in score if p in c.columns]].sum(axis=1).reindex(ends).ffill().fillna(0.0).to_numpy()
        blocks.extend(np.diff(np.r_[0.0, v]).tolist())
    return (unit, str(change), str(stress)), np.array(blocks)


if __name__ == "__main__":
    jobs = []
    for unit in UNITS:
        jobs.append((unit, None, {}))
        for s in range(5):
            jobs.append((unit, None, dict(passive_fill_rate=0.95, seed=s)))
        for ch in ALTS[unit]:
            jobs.append((unit, ch, {}))
    jobs.sort(key=lambda j: j[0] != "options")  # slow ones first
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        R = dict(ex.map(run, jobs))

    rows, bands = [], {}
    for unit in UNITS:
        base = R[(unit, "None", "{}")]
        noise = [R[(unit, "None", str(dict(passive_fill_rate=0.95, seed=s)))].sum() for s in range(5)]
        band = float(np.std(noise, ddof=1))
        bands[unit] = dict(unit=unit, base_total=base.sum(), noise_mean=np.mean(noise), noise_sd=band,
                           noise_range=max(noise) - min(noise))
        for ch in ALTS[unit]:
            alt = R[(unit, str(ch), "{}")]
            d = base - alt
            t = hac_mean_t(d)
            real = abs(d.sum()) > 2 * band and abs(t) >= 2
            rows.append(dict(unit=unit, chosen_vs=f"{ch[0]} = {ch[1]}", chosen_total=base.sum(), alt_total=alt.sum(),
                             chosen_minus_alt=d.sum(), noise_band_2sd=2 * band, blocks_chosen_better=float((d > 0).mean()),
                             paired_t=t, verdict=("chosen really better" if d.sum() > 0 else "alternative really better") if real
                             else "noise with an ordering"))
    B = pd.DataFrame(bands.values())
    C = pd.DataFrame(rows)
    pd.set_option("display.width", 230)
    print("Noise band: chosen setting rerun with a random 5% of passive fills dropped (5 seeds)")
    print(B.round(0).to_string(index=False))
    print("\nChosen setting vs nearest alternatives (paired over the same 30 blocks)")
    print(C.round(2).to_string(index=False))
    B.round(1).to_csv(os.path.join(OUT, "06_noise_band.csv"), index=False)
    C.round(3).to_csv(os.path.join(OUT, "06_fragility_comparisons.csv"), index=False)
