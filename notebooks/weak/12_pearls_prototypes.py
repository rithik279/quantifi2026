# %% [markdown]
# # Pearls prototype: lean WHITE / BLACK / BLUE quotes with a cross-pearl prediction
# Finding (11_pearls_deep.py): WHITE's and BLACK's next 20-tick moves are predictable from the OTHER
# pearls (out-of-sample corr ~0.1 on every day), BLUE's from its own momentum (~0.15-0.23).
# The predicted move is usually smaller than half the spread, so it's used to lean fair value
# (fair = mid + c x predicted 20-tick move), which mostly decides which side we quote.
#
# Honest test: the model's coefficients are fit on days -2 and -1 ONLY, then frozen. Day 0 is unseen.
# Features are computed live, tick by tick, exactly as a submission would (recursive EMAs, no lookahead).
# Run from repo root:  python notebooks/weak/12_pearls_prototypes.py

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
import data  # noqa: E402
import pearls  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
PE = pearls.PEARLS
H = 20
ALPHA = 2 / 21  # EMA span 20, recursive (same as live)


def feature_names():
    names = []
    for p in PE:
        names += [f"{p}_r1", f"{p}_r5", f"{p}_r20", f"{p}_gap"]
    return names + ["sumdev", "sumdev_r5"]


def features_from_history(hist, ema):
    """hist: deque of dicts {pearl: mid}, newest last (>= 21 entries). ema: {pearl: ema}."""
    now, f = hist[-1], []
    for p in PE:
        f += [now[p] - hist[-2][p], now[p] - hist[-6][p], now[p] - hist[-21][p], now[p] - ema[p]]
    s_now = sum(now.values()) - 50_000
    s_5 = sum(hist[-6].values()) - 50_000
    return f + [s_now, s_now - s_5]


def build_training():
    """Compute the live features for days -2 and -1 (per day, warm-up dropped) and fit one linear
    model per pearl for the next-20-tick move."""
    P = data.prices((-2, -1))
    mids = data.wide(P, products=PE)[PE]
    day = mids.index // 10_000
    Xs, Ys = [], {p: [] for p in PE}
    for d in sorted(set(day)):
        m = mids[day == d]
        hist, ema, rows = deque(maxlen=21), {}, []
        vals = m.to_dict("records")
        for i, row in enumerate(vals):
            for p in PE:
                ema[p] = row[p] if p not in ema else ALPHA * row[p] + (1 - ALPHA) * ema[p]
            hist.append(row)
            if len(hist) == 21 and i + H < len(vals):
                rows.append(features_from_history(hist, ema))
                for p in PE:
                    Ys[p].append(vals[i + H][p] - row[p])
        Xs += rows
    X = np.column_stack([np.array(Xs), np.ones(len(Xs))])
    return {p: np.linalg.lstsq(X, np.array(Ys[p]), rcond=None)[0] for p in PE}


COEF = None


class LeanedPearls(pearls.Trader):
    """pearls engine, but `lean` pearls get fair = mid + c x predicted 20-tick move."""

    def __init__(self, coef, lean, c, prm_over=None):
        prm = {p: dict(pearls.PARAMS[p], **(prm_over or {}).get(p, {})) for p in lean}
        super().__init__(prm)
        self.coef, self.lean, self.c = coef, lean, c
        self.hist, self.ema, self.pred = deque(maxlen=21), {}, {}

    def run(self, state):
        depths = state.order_depths
        if all(p in depths and depths[p].buy_orders and depths[p].sell_orders for p in PE):
            row = {p: (max(depths[p].buy_orders) + min(depths[p].sell_orders)) / 2 for p in PE}
            for p in PE:
                self.ema[p] = row[p] if p not in self.ema else ALPHA * row[p] + (1 - ALPHA) * self.ema[p]
            self.hist.append(row)
            if len(self.hist) == 21:
                x = np.array(features_from_history(self.hist, self.ema) + [1.0])
                self.pred = {p: float(x @ self.coef[p]) for p in self.lean}
        return super().run(state)

    def fair_value(self, product, mids):
        base = super().fair_value(product, mids)
        return base + self.c * self.pred.get(product, 0.0)


def evaluate(job):
    pearl, c, cap = job
    over = {pearl: dict(soft_cap=cap)}
    res = bt.backtest(lambda: LeanedPearls(COEF_G, [pearl], c, over), (-2, -1, 0), PE, record_every=0)
    return dict(pearl=pearl, c=c, cap=cap, **{f"d{d.day}": d.pnl_by_product.get(pearl, 0.0) for d in res.days})


def _init(coef):
    global COEF_G
    COEF_G = coef


if __name__ == "__main__":
    coef = build_training()
    names = feature_names() + ["const"]
    for p in ("WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS"):
        top = sorted(zip(names, coef[p]), key=lambda kv: -abs(kv[1]))[:5]
        print(f"{p} (trained on days -2/-1) largest coefficients: " + ", ".join(f"{n} {v:+.3f}" for n, v in top))
    jobs = list(itertools.product(["WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS"], [0.0, 0.5, 1.0, 2.0, 3.0], [5, 10, 20]))
    with ProcessPoolExecutor(initializer=_init, initargs=(coef,)) as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["train"] = df.d_2 + df.d_1
    df["total"] = df.train + df.d0
    df.to_csv(os.path.join(OUT, "20_pearls_leaned_mm.csv"), index=False)
    pd.set_option("display.width", 200)
    for p in ("WHITE_PEARLS", "BLACK_PEARLS", "BLUE_PEARLS"):
        d = df[df.pearl == p].pivot_table(index="c", columns="cap", values=["d_2", "d_1", "d0"]).round(0)
        print(f"\n=== {p}: PnL by lean strength c (rows) and inventory cap (columns); c=0 is today's engine ===")
        print(d.to_string())
