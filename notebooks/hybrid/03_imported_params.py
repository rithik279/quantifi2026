# %% [markdown]
# # Hybrid: are trader_v4's parameters validated or fitted?
# The two imported pieces come with numbers we didn't choose. Same checks as notebooks/stats (items 5-6):
#   - a grid around each chosen value, PnL per day (is the choice on a plateau or a peak?)
#   - leave-one-day-out: pick the config with the best worst training day, score it on the held-out day;
#     is the chosen config in the top quartile on every held-out day?
# Grids: TELLURIUM jump-drift w x H x jk (90 configs), smile options smile_span x take (25 configs).
# Run from repo root:  python notebooks/hybrid/03_imported_params.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import smile  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "hybrid")
OPT = [smile.UNDERLYING] + list(smile.VOUCHERS)
DAYS = ["d_2", "d_1", "d0"]
TELL_GRID = [dict(w=w, H=H, jk=jk) for w in (10, 15, 20, 25, 30, 40) for H in (150, 200, 250, 300, 400) for jk in (4.0, 5.5, 8.0)]
OPT_GRID = [dict(smile_span=s, take=k) for s in (10, 25, 50, 100, 200) for k in (2.0, 2.5, 3.0, 3.5, 4.0)]
CHOSEN = {"TELLURIUM": dict(w=20, H=250, jk=5.5), "OPTIONS": dict(smile_span=50, take=3.0)}


def job(j):
    unit, cfg = j
    if unit == "TELLURIUM":
        prm = dict(standalone.PARAMS["TELLURIUM"])
        prm["jumpdrift"] = dict(standalone.JUMPDRIFT, **cfg)
        res = bt.backtest(lambda: standalone.Trader({"TELLURIUM": prm}), (-2, -1, 0), ["TELLURIUM"], record_every=0)
    else:
        res = bt.backtest(lambda: smile.Trader(cfg), (-2, -1, 0), OPT, record_every=0)
    return dict(unit=unit, label=str(cfg), **cfg, **{k: d.total for k, d in zip(DAYS, res.days)})


def lodo(df, chosen):
    rows = []
    for held in DAYS:
        train = [d for d in DAYS if d != held]
        score = df[train].min(axis=1) * 1e6 + df[train].sum(axis=1)
        pick = df.loc[score.idxmax()]
        ch = df[df.label == chosen].iloc[0]
        rows.append(dict(held_out=held, lodo_pick=pick.label, lodo_pick_heldout=pick[held], ours_heldout=ch[held],
                         ours_percentile=(df[held] < ch[held]).mean() + 0.5 * (df[held] == ch[held]).mean(),
                         best_heldout=df[held].max()))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    jobs = [("OPTIONS", c) for c in OPT_GRID] + [("TELLURIUM", c) for c in TELL_GRID]
    with ProcessPoolExecutor() as ex:
        R = pd.DataFrame(list(ex.map(job, jobs)))
    R["total"] = R[DAYS].sum(axis=1)
    R["worst_day"] = R[DAYS].min(axis=1)
    R.round(1).to_csv(os.path.join(OUT, "03_imported_param_grid.csv"), index=False)
    pd.set_option("display.width", 220)

    t = R[R.unit == "TELLURIUM"]
    print("TELLURIUM jump-drift: total (k coins) by wait w x hold H, one table per jk")
    for jk in (4.0, 5.5, 8.0):
        print(f"\n  jk = {jk}")
        print((t[t.jk == jk].pivot(index="w", columns="H", values="total") / 1e3).round(1).to_string())
    print("\n  worst day (k coins), jk = 5.5")
    print((t[t.jk == 5.5].pivot(index="w", columns="H", values="worst_day") / 1e3).round(1).to_string())
    o = R[R.unit == "OPTIONS"]
    print("\nSmile options: total (k coins) by smile_span x take")
    print((o.pivot(index="smile_span", columns="take", values="total") / 1e3).round(1).to_string())
    print("  worst day (k coins)")
    print((o.pivot(index="smile_span", columns="take", values="worst_day") / 1e3).round(1).to_string())

    print("\nLeave-one-day-out")
    for unit, df in (("TELLURIUM", t), ("OPTIONS", o)):
        L = lodo(df.reset_index(drop=True), str(CHOSEN[unit]))
        ok = bool((L.ours_percentile >= 0.75).all() and (L.lodo_pick_heldout > 0).all())
        print(f"\n=== {unit} ({len(df)} configs), chosen {CHOSEN[unit]} -> {'VALIDATED' if ok else 'NOT validated'}")
        print(L.round(2).to_string(index=False))
        L.round(3).to_csv(os.path.join(OUT, f"03_lodo_{unit}.csv"), index=False)
