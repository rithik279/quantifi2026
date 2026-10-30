# %% [markdown]
# # TELLURIUM spike-fade and RSI backtests (prototypes, TELLURIUM only, no market making)
# A. naive fade: after a spike (>= J coins within 5 ticks), wait D ticks, then fade it with 40 units.
#    Exit when price is back a fraction f of the way to the pre-spike level, after H ticks, or at a
#    stop if it runs a further `stop` x spike size against us.
# B. confirmed fade: after a spike, track the running extreme; only fade once price has already come
#    back c x spike size from that extreme. Exit at fraction f back to the pre-spike level, after H
#    ticks, or stop out if price makes a new extreme.
# C. RSI: short when RSI(n) > level (and, optionally, buy when RSI < 100 - level); exit when RSI
#    crosses 50 or after H ticks.
# D. ride (the opposite of the idea, added after A-C failed): go WITH the spike for H ticks, because
#    the spike study shows it keeps going ~20-55% of its size in the first 100 ticks on every day.
# All take liquidity (cross the spread, ~9 coins round trip). Day 0 is the honest check for any rule
# whose numbers came from the spike study, but with ~10 spikes a day everything here is thin evidence.
# Run from repo root:  python notebooks/weak/07_tellurium_fade_backtest.py

# %%
import itertools
import os
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import backtester as bt  # noqa: E402
from datamodel import Order  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
PROD, LIMIT, L = "TELLURIUM", 40, 5


def move_to(depth, pos, target):
    target = max(-LIMIT, min(LIMIT, target))
    diff, orders = target - pos, []
    if diff > 0:
        for a in sorted(depth.sell_orders):
            if diff <= 0:
                break
            q = min(diff, -depth.sell_orders[a]); orders.append(Order(PROD, a, q)); diff -= q
    elif diff < 0:
        for b in sorted(depth.buy_orders, reverse=True):
            if diff >= 0:
                break
            q = min(-diff, depth.buy_orders[b]); orders.append(Order(PROD, b, -q)); diff += q
    return orders


class SpikeFade:
    def __init__(self, mode="naive", J=60, D=0, f=1.0, H=1000, stop=None, c=0.2, cool=200):
        self.mode, self.J, self.D, self.f, self.H, self.stop, self.c, self.cool = mode, J, D, f, H, stop, c, cool
        self.hist = deque(maxlen=L + 1)
        self.spike = None   # dict(pre, size, dirn, peak, t0)
        self.trade = None   # dict(entry, target, stopx, t_in, side)
        self.last_end = -10**9

    def run(self, state):
        d = state.order_depths[PROD]
        mid = (max(d.buy_orders) + min(d.sell_orders)) / 2
        t = state.timestamp // 100
        self.hist.append(mid)
        pos = state.position.get(PROD, 0)
        target = pos

        if self.trade is not None:
            tr = self.trade
            done = (t - tr["t_in"] >= self.H
                    or (tr["side"] < 0 and mid <= tr["target"]) or (tr["side"] > 0 and mid >= tr["target"])
                    or (tr["stopx"] is not None and ((tr["side"] < 0 and mid >= tr["stopx"]) or (tr["side"] > 0 and mid <= tr["stopx"]))))
            if done:
                target, self.trade, self.spike, self.last_end = 0, None, None, t
            else:
                target = tr["side"] * LIMIT
        else:
            if self.spike is None and len(self.hist) == L + 1 and t - self.last_end >= self.cool:
                mv = self.hist[-1] - self.hist[0]
                if abs(mv) >= self.J:
                    self.spike = dict(pre=self.hist[0], size=abs(mv), dirn=1 if mv > 0 else -1, peak=mid, t0=t)
            if self.spike is not None:
                s = self.spike
                s["peak"] = max(s["peak"], mid) if s["dirn"] > 0 else min(s["peak"], mid)
                if t - s["t0"] > max(self.D, 1) + 2000:  # never triggered: forget it
                    self.spike = None
                elif self.mode == "ride" and t - s["t0"] >= self.D:
                    # go WITH the spike; exit after H ticks (target/stop disabled unless stop given)
                    side = s["dirn"]
                    stopx = mid - s["dirn"] * self.stop * s["size"] if self.stop else None
                    self.trade = dict(entry=mid, target=float("inf") * side, stopx=stopx, t_in=t, side=side)
                    target = side * LIMIT
                elif self.mode == "naive" and t - s["t0"] >= self.D:
                    side = -s["dirn"]
                    tgt = s["peak"] - s["dirn"] * self.f * (s["peak"] - s["pre"])
                    stopx = mid + s["dirn"] * self.stop * s["size"] if self.stop else None
                    self.trade = dict(entry=mid, target=tgt, stopx=stopx, t_in=t, side=side)
                    target = side * LIMIT
                elif self.mode == "confirmed" and s["dirn"] * (s["peak"] - mid) >= self.c * s["size"]:
                    side = -s["dirn"]
                    tgt = s["peak"] - s["dirn"] * self.f * abs(s["peak"] - s["pre"])
                    self.trade = dict(entry=mid, target=tgt, stopx=s["peak"], t_in=t, side=side)
                    target = side * LIMIT
        out = {PROD: move_to(d, pos, target)} if target != pos else {}
        return out, 0, ""


class RSITrader:
    def __init__(self, n=50, level=70, both=False, H=1000):
        self.a, self.level, self.both, self.H = 1 / n, level, both, H
        self.up = self.dn = None
        self.prev = None
        self.side, self.t_in = 0, 0

    def run(self, state):
        d = state.order_depths[PROD]
        mid = (max(d.buy_orders) + min(d.sell_orders)) / 2
        t = state.timestamp // 100
        if self.prev is None:
            self.prev, self.up, self.dn = mid, 0.0, 0.0
        ch = mid - self.prev; self.prev = mid
        self.up = (1 - self.a) * self.up + self.a * max(ch, 0)
        self.dn = (1 - self.a) * self.dn + self.a * max(-ch, 0)
        r = 50 if self.up + self.dn == 0 else 100 * self.up / (self.up + self.dn)
        pos = state.position.get(PROD, 0)
        if self.side == 0:
            if r > self.level:
                self.side, self.t_in = -1, t
            elif self.both and r < 100 - self.level:
                self.side, self.t_in = 1, t
        elif t - self.t_in >= self.H or (self.side < 0 and r < 50) or (self.side > 0 and r > 50):
            self.side = 0
        target = self.side * LIMIT
        return ({PROD: move_to(d, pos, target)} if target != pos else {}), 0, ""


def evaluate(job):
    kind, kw = job
    factory = (lambda: SpikeFade(**kw)) if kind != "rsi" else (lambda: RSITrader(**kw))
    res = bt.backtest(factory, (-2, -1, 0), [PROD], record_every=0)
    return dict(kind=kind, params=str(kw), **{f"d{d.day}": d.pnl_by_product.get(PROD, 0.0) for d in res.days})


if __name__ == "__main__":
    jobs = []
    for J, D, f, H, stop in itertools.product([60, 100], [0, 100, 200], [0.5, 1.0], [500, 1500], [None, 0.5]):
        jobs.append(("naive", dict(mode="naive", J=J, D=D, f=f, H=H, stop=stop)))
    for J, c, f, H in itertools.product([60, 100], [0.1, 0.2, 0.35], [0.5, 0.8, 1.0], [1000, 3000]):
        jobs.append(("confirmed", dict(mode="confirmed", J=J, c=c, f=f, H=H)))
    for n, level, both, H in itertools.product([50, 200], [70, 80], [False, True], [500, 1000]):
        jobs.append(("rsi", dict(n=n, level=level, both=both, H=H)))
    for J, D, H, stop in itertools.product([60, 100], [0, 5], [50, 100, 200, 300], [None, 0.5]):
        jobs.append(("ride", dict(mode="ride", J=J, D=D, H=H, stop=stop)))
    print(f"{len(jobs)} backtests")
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs, chunksize=2))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    df["positive_days"] = (df[["d_2", "d_1", "d0"]] > 0).sum(axis=1)
    df.to_csv(os.path.join(OUT, "13_tellurium_fade_backtests.csv"), index=False)
    pd.set_option("display.width", 230); pd.set_option("display.max_colwidth", 90)
    for kind in ("naive", "confirmed", "rsi", "ride"):
        d = df[df.kind == kind].sort_values("min_day", ascending=False)
        print(f"\n=== {kind}: {len(d)} settings, {int((d.positive_days == 3).sum())} positive on all 3 days, "
              f"median total {d.total.median():,.0f} ===")
        print(d.head(6)[["params", "d_2", "d_1", "d0", "total"]].round(0).to_string(index=False))
