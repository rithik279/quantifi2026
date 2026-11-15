# %% [markdown]
# # PB & J coordinated passive market maker (ChatGPT's proposal, tested as written)
# 1. Quote JELLY passively at the best bid/ask (its 11-coin spread gives the cushion), inventory cap jcap.
# 2. PB is only a hedge: common-factor exposure F = PB position + 0.41 x JELLY position,
#    hedge target PB = -0.41 x JELLY position.
# 3. Hedge only outside a band: when |target - PB position| >= band, post a PASSIVE PB order at the
#    best bid/ask for the difference. Never cross.
# 4. If F is still beyond the band, stop quoting the JELLY side that would make it worse.
# 5. Optional stale-leg filter: u = 0.41 x dPB - dJELLY over the last k ticks. u > thr means JELLY has
#    lagged PB upward, so don't quote the JELLY ask; u < -thr, don't quote the JELLY bid.
# Compared with the current submission (JELLY and PB market-made independently), per day, plus the
# reduced-fill stress for the best settings.
# Run from repo root:  python notebooks/weak/10_pbj_coordinated_mm.py

# %%
import itertools
import os
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import standalone  # noqa: E402
from datamodel import Order  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
J, PB, BETA = "JELLY", "PEANUT_BUTTER", 0.41
PRODUCTS = [J, PB]


class PBJMM:
    def __init__(self, jcap=5, band=4, hedge=True, filt=False, k=5, thr=2.0):
        self.jcap, self.band, self.hedge, self.filt, self.k, self.thr = jcap, band, hedge, filt, k, thr
        self.hj, self.hp = deque(maxlen=k + 1), deque(maxlen=k + 1)
        self.F = []

    def run(self, state):
        dj, dp = state.order_depths[J], state.order_depths[PB]
        jb, ja, pb_b, pb_a = max(dj.buy_orders), min(dj.sell_orders), max(dp.buy_orders), min(dp.sell_orders)
        mj, mp = (jb + ja) / 2, (pb_b + pb_a) / 2
        self.hj.append(mj); self.hp.append(mp)
        jpos, ppos = state.position.get(J, 0), state.position.get(PB, 0)
        F = ppos + BETA * jpos
        self.F.append(F)
        out = {}

        # PB: passive hedge only, outside the band
        if self.hedge:
            err = int(round(-BETA * jpos)) - ppos
            if err >= self.band:
                out[PB] = [Order(PB, pb_b, min(err, 50 - ppos))]
            elif err <= -self.band:
                out[PB] = [Order(PB, pb_a, -min(-err, 50 + ppos))]

        # JELLY: passive at the touch, capped, with the factor guard and optional stale-leg filter
        quote_bid, quote_ask = True, True
        if self.hedge and F > self.band:
            quote_bid = False          # buying JELLY would add to a long factor exposure
        if self.hedge and F < -self.band:
            quote_ask = False
        if self.filt and len(self.hj) == self.k + 1:
            u = BETA * (self.hp[-1] - self.hp[0]) - (self.hj[-1] - self.hj[0])
            if u > self.thr:
                quote_ask = False      # JELLY lagged PB upward: keep the bid, drop the ask
            elif u < -self.thr:
                quote_bid = False
        orders = []
        if quote_bid and self.jcap - jpos > 0:
            orders.append(Order(J, jb, self.jcap - jpos))
        if quote_ask and self.jcap + jpos > 0:
            orders.append(Order(J, ja, -(self.jcap + jpos)))
        if orders:
            out[J] = orders
        return out, 0, ""


def evaluate(job):
    name, kw, stress = job
    traders = []

    def factory():
        if kw is None:
            return standalone.Trader({p: standalone.PARAMS[p] for p in PRODUCTS})
        t = PBJMM(**kw); traders.append(t); return t

    res = bt.backtest(factory, (-2, -1, 0), PRODUCTS, record_every=0, **stress)
    row = dict(variant=name, stress=str(stress) if stress else "",
               **{f"d{d.day}": d.total for d in res.days},
               jelly=sum(d.pnl_by_product.get(J, 0) for d in res.days),
               pb=sum(d.pnl_by_product.get(PB, 0) for d in res.days),
               jelly_units=sum(d.volume.get(J, 0) for d in res.days),
               pb_units=sum(d.volume.get(PB, 0) for d in res.days))
    row["mean_abs_factor"] = float(np.mean(np.abs(np.concatenate([t.F for t in traders])))) if traders else float("nan")
    return row


if __name__ == "__main__":
    jobs = [("current (independent MM)", None, {})]
    for jcap, filt in itertools.product([3, 5, 10], [False, True]):
        jobs.append((f"JELLY only, cap {jcap}, filter {filt}", dict(jcap=jcap, hedge=False, filt=filt), {}))
    for jcap, band, filt in itertools.product([3, 5, 10], [2, 4, 6], [False, True]):
        jobs.append((f"coordinated, cap {jcap}, band {band}, filter {filt}", dict(jcap=jcap, band=band, filt=filt), {}))
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    pd.set_option("display.width", 240); pd.set_option("display.max_colwidth", 60)
    print(df.sort_values("min_day", ascending=False).round(1).to_string(index=False))

    # reduced-fill stress for the current version and the best three by worst day
    top = df[df.variant != "current (independent MM)"].sort_values("min_day", ascending=False).head(3).variant.tolist()
    kws = {name: kw for name, kw, _ in jobs}
    sjobs = [(n, kws[n], dict(passive_fill_rate=0.5, seed=s)) for n in ["current (independent MM)"] + top for s in (0, 1)]
    with ProcessPoolExecutor() as ex:
        sdf = pd.DataFrame(list(ex.map(evaluate, sjobs))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    sdf["total"] = sdf[["d_2", "d_1", "d0"]].sum(axis=1)
    print("\nWith only 50% of eligible trades filling us (mean of 2 seeds):")
    print(sdf.groupby("variant", sort=False)[["d_2", "d_1", "d0", "total"]].mean().round(0).to_string())
    pd.concat([df, sdf]).to_csv(os.path.join(OUT, "17_pbj_coordinated_mm.csv"), index=False)
