# %% [markdown]
# # Item 7: options "lie detector": is the options PnL a pricing edge, or LYCHEE direction / luck?
# A. Attribution. Record the book every tick (positions, LYCHEE mid, each voucher's Black-Scholes delta
#    from the trader's own implied vols) and split PnL exactly into:
#      entry edge = sum over fills of side x qty x (mid at fill - fill price)   [captured when trading]
#      direction  = net delta held x LYCHEE's move, tick by tick               [LYCHEE direction]
#      pricing    = everything else in the vouchers' moves while held          [convergence to fair,
#                                                                               gamma/vega/theta]
#    entry + direction + pricing = backtest PnL (checked).
# B. Naive baselines, paired on 30 blocks, to measure what Black-Scholes actually contributes
#    ("the diagnostic is the gap, not the level"):
#      - fair = slow EMA of each voucher's own mid (same 1,000-tick memory, same take/make rules, no BS)
#      - fair = current mid (pure passive market making at the touch)
#    compared with the real book, all UNHEDGED so the comparison is pricing vs pricing.
# Run from repo root:  python notebooks/stats/06_options_attribution.py

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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402
from stats_lib import block_stats, hac_mean_t, sign_test_p  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "stats")
OPT = [options.UNDERLYING] + list(options.VOUCHERS)
U = options.UNDERLYING
BLOCK_TS = 100_000


class Recording(options.Trader):
    def __init__(self, prm=None):
        super().__init__(prm)
        self.rec = []

    def run(self, state):
        out = super().run(state)
        mem = json.loads(out[2])
        und = state.order_depths[U]
        S = (max(und.buy_orders) + min(und.sell_orders)) / 2
        T = self.tte(state.timestamp)
        deltas = {p: options.bs_delta(S, K, T, mem["iv"][p]) if p in mem.get("iv", {}) else 0.0
                  for p, K in options.VOUCHERS.items()}
        self.rec.append(dict(pos=dict(state.position), deltas=deltas))
        return out


class EmaNaive(options.Trader):
    """No Black-Scholes: each voucher's fair value is a slow EMA of its own mid. Same take/make, no hedge."""

    def run(self, state):
        prm = self.params
        mem = json.loads(state.traderData) if state.traderData else {}
        ema, rv = mem.setdefault("ema", {}), mem.setdefault("rv", {})
        a = 2 / (prm["iv_span"] + 1)
        result = {}
        for product in options.VOUCHERS:
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue
            vmid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            ema[product] = vmid if product not in ema else a * vmid + (1 - a) * ema[product]
            if vmid < prm["min_price"]:
                continue
            fair = ema[product]
            resid = vmid - fair
            b = 2 / (prm["resid_span"] + 1)
            rv[product] = b * resid * resid + (1 - b) * rv.get(product, resid * resid)
            take = max(prm["take_min"], prm["take_k"] * math.sqrt(rv[product])) if prm["take_mode"] == "scaled" else prm["take_edge"]
            result[product] = self.quote(product, depth, state.position.get(product, 0), fair, take)
        return result, 0, json.dumps(mem)


class MidNaive(options.Trader):
    """No fair-value model at all: quote at the touch around the current mid (never takes). No hedge."""

    def run(self, state):
        result = {}
        for product in options.VOUCHERS:
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue
            vmid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            if vmid < self.params["min_price"]:
                continue
            result[product] = self.quote(product, depth, state.position.get(product, 0), vmid, 1e9)
        return result, 0, ""


def blocks(res):
    out = []
    for d in res.days:
        c = d.pnl_curve.drop(columns="TOTAL", errors="ignore")
        ends = sorted(set([ts for ts in c.index if ts % BLOCK_TS == 0 and ts > 0] + [c.index[-1]]))
        v = c.sum(axis=1).reindex(ends).ffill().fillna(0.0).to_numpy()
        out.extend(np.diff(np.r_[0.0, v]).tolist())
    return np.array(out)


def attribution(hedge):
    traders = []

    def f():
        t = Recording(dict(hedge=hedge)); traders.append(t); return t

    res = bt.backtest(f, (-2, -1, 0), OPT, record_every=100, keep_fills=True)
    rows = []
    for t, d in zip(traders, res.days):
        data = bt.get_day(d.day, OPT)
        idx = {ts: i for i, ts in enumerate(data.timestamps)}
        m = data.mids
        entry = sum(f["side"] * f["qty"] * (m[f["product"]][idx[f["ts"]]] - f["price"]) for f in d.fills)
        inv = direction = 0.0
        S = m[U]
        n = len(data.timestamps)
        for i in range(n - 1):
            after = t.rec[i + 1]["pos"]  # position after the fills of tick i
            dS = S[i + 1] - S[i]
            inv += sum(q * (m[p][i + 1] - m[p][i]) for p, q in after.items())
            net_delta = after.get(U, 0) + sum(after.get(p, 0) * t.rec[i]["deltas"].get(p, 0.0) for p in options.VOUCHERS)
            direction += net_delta * dS
        rows.append(dict(hedge=hedge, day=d.day, entry_edge=entry, lychee_direction=direction, pricing=inv - direction,
                         total=entry + inv, backtest_total=d.total, lychee_leg=d.pnl_by_product.get(U, 0.0)))
    return rows, blocks(res)


def naive(kind):
    cls = {"ema": EmaNaive, "mid": MidNaive}[kind]
    res = bt.backtest(lambda: cls(dict(hedge=False)), (-2, -1, 0), OPT, record_every=100)
    return kind, blocks(res)


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        fa = [ex.submit(attribution, True), ex.submit(attribution, False)]
        fn = [ex.submit(naive, "ema"), ex.submit(naive, "mid")]
        (rows_h, b_h), (rows_u, b_u) = fa[0].result(), fa[1].result()
        nv = dict(f.result() for f in fn)
    A = pd.DataFrame(rows_h + rows_u)
    tot = A.groupby("hedge")[["entry_edge", "lychee_direction", "pricing", "total", "backtest_total", "lychee_leg"]].sum()
    pd.set_option("display.width", 220)
    print("A. Options PnL split (coins). total = entry + direction + pricing; backtest_total is the check")
    print(A.round(0).to_string(index=False))
    print("\nOver 3 days:")
    print(tot.round(0).to_string())
    A.round(1).to_csv(os.path.join(OUT, "07_options_attribution.csv"), index=False)

    print("\nB. Book vs naive versions over 30 blocks (all unhedged)")
    rows = [dict(series="Black-Scholes book (unhedged)", **block_stats(b_u)),
            dict(series="Black-Scholes book (hedged, as submitted)", **block_stats(b_h)),
            dict(series="naive: fair = slow EMA of own mid", **block_stats(nv["ema"])),
            dict(series="naive: fair = current mid (passive only)", **block_stats(nv["mid"]))]
    S = pd.DataFrame(rows)
    print(S[["series", "total", "hit_rate", "t_hac", "sign_p"]].round(3).to_string(index=False))
    pairs = []
    for name, other in (("BS vs slow-EMA fair", nv["ema"]), ("BS vs current-mid fair", nv["mid"]), ("hedged vs unhedged BS", None)):
        d = (b_h - b_u) if other is None else (b_u - other)
        pairs.append(dict(comparison=name, diff_total=d.sum(), blocks_better=float((d > 0).mean()), t_hac=hac_mean_t(d), sign_p=sign_test_p(d)))
    Pp = pd.DataFrame(pairs)
    print("\nPaired over the same 30 blocks:")
    print(Pp.round(3).to_string(index=False))
    S.round(3).to_csv(os.path.join(OUT, "07_options_vs_naive.csv"), index=False)
    Pp.round(3).to_csv(os.path.join(OUT, "07_options_vs_naive_paired.csv"), index=False)
