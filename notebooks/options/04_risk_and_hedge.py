# %% [markdown]
# # Options: how much LYCHEE risk does the unhedged book carry, and does a wide-band hedge help?
# Wraps the trader to record net option delta every tick (from state.position).
# Run from repo root:  python notebooks/options/04_risk_and_hedge.py

# %%
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "options")
PRODUCTS = [options.UNDERLYING] + list(options.VOUCHERS)
VARIANTS = {
    "unhedged": dict(hedge=False),
    "hedge_band60": dict(hedge=True, hedge_band=60),
    "hedge_band120": dict(hedge=True, hedge_band=120),
}


class Recording(options.Trader):
    def __init__(self, params):
        super().__init__(params)
        self.deltas = []

    def run(self, state):
        out = super().run(state)
        mem = __import__("json").loads(out[2])
        und = state.order_depths[options.UNDERLYING]
        S = (max(und.buy_orders) + min(und.sell_orders)) / 2
        T = self.tte(state.timestamp)
        d = sum(state.position.get(p, 0) * options.bs_delta(S, K, T, mem["iv"].get(p, 0.02))
                for p, K in options.VOUCHERS.items())
        self.deltas.append((d, state.position.get(options.UNDERLYING, 0)))
        return out


def run(name):
    traders = []

    def factory():
        t = Recording(VARIANTS[name]); traders.append(t); return t

    res = bt.backtest(factory, (-2, -1, 0), PRODUCTS, record_every=100)
    deltas = [np.array(t.deltas) for t in traders]
    return name, {d.day: d.total for d in res.days}, {d.day: d.pnl_by_product.get("LYCHEE", 0.0) for d in res.days}, deltas, [d.pnl_curve["TOTAL"].to_numpy() for d in res.days]


if __name__ == "__main__":
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(run, VARIANTS))
    fig, axes = plt.subplots(2, 1, figsize=(12, 6))
    for name, pnl, lych, deltas, curves in results:
        net = np.concatenate([d[:, 0] + d[:, 1] for d in deltas])
        print(f"{name:14s} PnL by day {({k: round(v) for k, v in pnl.items()})}  total {sum(pnl.values()):,.0f}"
              f"  (LYCHEE leg {sum(lych.values()):,.0f})")
        print(f"{'':14s} net delta: mean {net.mean():+.1f}, mean |delta| {np.abs(net).mean():.1f}, 95th pct |delta| {np.percentile(np.abs(net), 95):.0f}, max {np.abs(net).max():.0f}")
        axes[0].plot(net, lw=0.4, label=name)
        off, xs, ys = 0.0, [], []
        for i, c in enumerate(curves):
            ys.append(c + off); xs.append(np.arange(len(c)) + i * len(c)); off += c[-1]
        axes[1].plot(np.concatenate(xs), np.concatenate(ys), lw=0.8, label=name)
    axes[0].set_title("Net delta (vouchers + LYCHEE), LYCHEE-equivalent units"); axes[0].legend(fontsize=7)
    axes[1].set_title("Cumulative PnL (days -2, -1, 0)"); axes[1].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "07_delta_and_pnl.png"), dpi=110)
    # 1-sigma daily LYCHEE move ~ 1.6% x 7,440 ~ 120 coins: mean |delta| x 120 ~ typical daily PnL risk
