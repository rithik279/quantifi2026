# %% [markdown]
# # Prototypes for the new ideas (not in the submission yet)
# 1. PB & JELLY pair trade: hold JELLY against its spread to PB, hedged with PB.
#        S = JELLY - beta x PB,  target JELLY = -clip((S - EMA_W(S)) / scale) x 50,  PB = -beta x JELLY
#    Taker strategy (crosses both spreads). The 1,000-tick EMA / 500-tick horizon was the one
#    combination whose sign held on all days in 04_pbj_pair.py.
# 2. BLUE_PEARLS momentum: its last 5 ticks predict the next 5 (corr +0.18..+0.21 every day).
#        fair = mid + c x (EMA_fast - EMA_slow), then the usual pearls market-making engine.
# Each is scored per day; day 0 is the honest check because W/beta/c come from all three days' scans.
# Run from repo root:  python notebooks/weak/05_prototypes.py

# %%
import itertools
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import pearls  # noqa: E402
from datamodel import Order  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
BETA = 0.412


class PairTrader:
    """JELLY vs PEANUT_BUTTER spread, mean reversion around a slow EMA, hedged."""

    def __init__(self, W=1000, scale=60.0, min_trade=5, hedge=True):
        self.alpha, self.scale, self.min_trade, self.hedge = 2 / (W + 1), scale, min_trade, hedge
        self.ema = None

    @staticmethod
    def _move(product, depth, pos, target, limit):
        target = max(-limit, min(limit, target))
        diff, orders = target - pos, []
        if diff > 0:
            for ask in sorted(depth.sell_orders):
                if diff <= 0:
                    break
                q = min(diff, -depth.sell_orders[ask]); orders.append(Order(product, ask, q)); diff -= q
        elif diff < 0:
            for b in sorted(depth.buy_orders, reverse=True):
                if diff >= 0:
                    break
                q = min(-diff, depth.buy_orders[b]); orders.append(Order(product, b, -q)); diff += q
        return orders

    def run(self, state):
        dj, dp = state.order_depths["JELLY"], state.order_depths["PEANUT_BUTTER"]
        mj = (max(dj.buy_orders) + min(dj.sell_orders)) / 2
        mp = (max(dp.buy_orders) + min(dp.sell_orders)) / 2
        s = mj - BETA * mp
        self.ema = s if self.ema is None else self.alpha * s + (1 - self.alpha) * self.ema
        dev = (s - self.ema) / self.scale
        tj = int(round(-max(-1.0, min(1.0, dev)) * 50))
        pj = state.position.get("JELLY", 0)
        out = {}
        if abs(tj - pj) >= self.min_trade:
            out["JELLY"] = self._move("JELLY", dj, pj, tj, 50)
        if self.hedge:
            tp = int(round(-BETA * pj))
            pp = state.position.get("PEANUT_BUTTER", 0)
            if abs(tp - pp) >= 2:
                out["PEANUT_BUTTER"] = self._move("PEANUT_BUTTER", dp, pp, tp, 50)
        return out, 0, ""


class BlueMomentum(pearls.Trader):
    """pearls engine, but BLUE's fair value leans in the direction of its recent move."""

    def __init__(self, c, fast=3, slow=15, prm=None):
        super().__init__({"BLUE_PEARLS": prm or pearls.PARAMS["BLUE_PEARLS"]})
        self.c, self.af, self.as_ = c, 2 / (fast + 1), 2 / (slow + 1)
        self.f = self.s = None

    def fair_value(self, product, mids):
        m = mids[product]
        self.f = m if self.f is None else self.af * m + (1 - self.af) * self.f
        self.s = m if self.s is None else self.as_ * m + (1 - self.as_) * self.s
        return m + self.c * (self.f - self.s)


def run_pair(args):
    W, scale, mt, hedge = args
    res = bt.backtest(lambda: PairTrader(W, scale, mt, hedge), (-2, -1, 0), ["JELLY", "PEANUT_BUTTER"], record_every=0)
    return dict(idea="PB&J pair", params=f"W={W} scale={scale} min_trade={mt} hedge={hedge}",
                **{f"d{d.day}": d.total for d in res.days})


def run_blue(args):
    c, fast, slow, cap, make = args
    prm = dict(pearls.PARAMS["BLUE_PEARLS"], soft_cap=cap, make_edge=make, take_edge=100)
    res = bt.backtest(lambda: BlueMomentum(c, fast, slow, prm), (-2, -1, 0), pearls.PEARLS, record_every=0)
    return dict(idea="BLUE momentum", params=f"c={c} ema={fast}/{slow} cap={cap} make={make}",
                **{f"d{d.day}": d.pnl_by_product.get("BLUE_PEARLS", 0.0) for d in res.days})


if __name__ == "__main__":
    pair_jobs = list(itertools.product([300, 1000, 2000], [30, 60, 120], [5], [True, False]))
    blue_jobs = list(itertools.product([0, 1, 2, 4], [3], [15, 50], [5, 20], [2, 3]))
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(run_pair, pair_jobs)) + list(ex.map(run_blue, blue_jobs))
    df = pd.DataFrame(rows).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    df.to_csv(os.path.join(OUT, "10_prototypes.csv"), index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 60)
    for idea in ("PB&J pair", "BLUE momentum"):
        d = df[df.idea == idea].sort_values("min_day", ascending=False)
        print(f"\n=== {idea} (sorted by worst day) ===")
        print(d[["params", "d_2", "d_1", "d0", "total"]].round(0).to_string(index=False))
