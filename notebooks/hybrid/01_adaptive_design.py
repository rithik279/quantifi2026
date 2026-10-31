# %% [markdown]
# # Hybrid: designing the adaptive guards for the two imported pieces
# The hybrid = best-366k with trader_v4's smile options book and TELLURIUM jump-drift. Both pieces carry a
# hard-coded assumption:
#   A. options take a voucher 3 coins through fair, a fixed coin amount. If wobbles get smaller or larger
#      on day 1, is a threshold scaled to the recent wobble size better? (best-366k's options already do this)
#   B. TELLURIUM assumes the price keeps drifting after a jump. If that stops, each trade pays the spread
#      for nothing. What do trade outcomes look like then, versus the real days?
# Run from repo root:  python notebooks/hybrid/01_adaptive_design.py

# %%
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import smile  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "hybrid")
os.makedirs(OUT, exist_ok=True)
OPT = [smile.UNDERLYING] + list(smile.VOUCHERS)
OPT_SCEN = ["real", "iv_x0.8", "iv_x1.2", "iv_wander_5pct", "iv_wander_10pct", "lychee_vol_x1.5"]
TAKES = [2.0, 2.4, 3.0, 3.6, 4.0]
TELL_SCEN = ["real", "tellurium_no_drift_1", "tellurium_no_drift_2", "bootstrap_1", "bootstrap_2", "bootstrap_3",
             "vol_x0.6", "vol_x1.5", "spread_+1", "mirror"]


class Scale(smile.Trader):
    """Records the book's wobble size: slow EMA of the mean |voucher mid - smile fair| (vouchers >= 3 coins)."""

    def __init__(self, prm=None):
        super().__init__(prm)
        self.trace = []

    def run(self, state):
        out = super().run(state)
        mem = json.loads(out[2])
        coef = mem.get("smile")
        und = state.order_depths[smile.UNDERLYING]
        S = (max(und.buy_orders) + min(und.sell_orders)) / 2
        if coef is not None:
            r = []
            for sym, K in smile.VOUCHERS.items():
                od = state.order_depths.get(sym)
                if od is None or not od.buy_orders or not od.sell_orders:
                    continue
                vm = (max(od.buy_orders) + min(od.sell_orders)) / 2
                if vm < 3:
                    continue
                m = math.log(K / S)
                v = max(coef[0] + coef[1] * m + coef[2] * m * m, 1e-4)
                r.append(abs(vm - smile.bs_call(S, K, v)))
            if r:
                x = sum(r) / len(r)
                self.ema = x if not hasattr(self, "ema") else self.ema + (x - self.ema) / 1000.0
                self.trace.append(self.ema)
        return out


def opt_job(job):
    scen, take = job
    traders = []

    def f():
        t = Scale({"take": take}); traders.append(t); return t
    res = bt.backtest(f, (-2, -1, 0), OPT, record_every=0, scenario=None if scen == "real" else scen)
    scale = [float(np.percentile(t.trace[2000:], q)) for t in traders for q in (5, 50, 95)]
    return dict(scenario=scen, take=take, d_2=res.days[0].total, d_1=res.days[1].total, d0=res.days[2].total,
                total=res.total, scale_p5_p50_p95_by_day=[round(s, 2) for s in scale])


def episodes(res):
    out = []
    for d in res.days:
        c = d.pnl_curve["TELLURIUM"]
        by_ts = {}
        for f in d.fills:
            by_ts[f["ts"]] = by_ts.get(f["ts"], 0) + f["side"] * f["qty"]
        pos, start = 0, None
        for ts in sorted(by_ts):
            new = pos + by_ts[ts]
            if pos == 0 and new != 0:
                start = ts
            if new == 0 and start is not None:
                prev = c[c.index < start]
                out.append(dict(day=d.day, start=start, end=ts, pnl=c.loc[ts] - (prev.iloc[-1] if len(prev) else 0.0)))
                start = None
            pos = new
    return out


def tell_job(scen):
    prm = {"TELLURIUM": standalone.PARAMS["TELLURIUM"]}
    res = bt.backtest(lambda: standalone.Trader(prm), (-2, -1, 0), ["TELLURIUM"], record_every=1, keep_fills=True,
                      scenario=None if scen == "real" else scen)
    return scen, [d.total for d in res.days], episodes(res)


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        fo = [ex.submit(opt_job, (s, k)) for s in OPT_SCEN for k in TAKES]
        ft = [ex.submit(tell_job, s) for s in TELL_SCEN]
        O = pd.DataFrame([f.result() for f in fo])
        T = [f.result() for f in ft]
    O.to_csv(os.path.join(OUT, "01_options_take_by_scenario.csv"), index=False)
    pd.set_option("display.width", 230)
    print("A. Smile options book: PnL by take threshold and scenario (k coins)")
    piv = O.pivot(index="scenario", columns="take", values="total").reindex(OPT_SCEN) / 1e3
    print(piv.round(1).to_string())
    print("\nWobble size (EMA of mean |mid - smile fair|), p5/p50/p95 per day, take 3:")
    print(O[O["take"] == 3.0][["scenario", "scale_p5_p50_p95_by_day"]].to_string(index=False))

    print("\nB. TELLURIUM jump-drift trades by scenario")
    rows, eps = [], []
    for scen, days, ep in T:
        e = pd.DataFrame(ep)
        e["scenario"] = scen
        eps.append(e)
        worst = {}
        for n in (2, 3, 4, 5):
            worst[f"worst_sum_last_{n}"] = min((e[e.day == d].pnl.rolling(n).sum().min() for d in (-2, -1, 0)
                                                if (e.day == d).sum() >= n), default=np.nan)
        rows.append(dict(scenario=scen, total=sum(days), trades=len(e), win=(e.pnl > 0).mean(), mean=e.pnl.mean(),
                         worst_trade=e.pnl.min(), **worst))
    R = pd.DataFrame(rows)
    print(R.round(2).to_string(index=False))
    pd.concat(eps).to_csv(os.path.join(OUT, "01_tellurium_trades_by_scenario.csv"), index=False)
