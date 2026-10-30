# %% [markdown]
# # GOLDEN_PEARLS: ride the slide between plateaus
# Seen on 19_golden_steps.png: GOLDEN doesn't jump between plateaus, it slides in a straight line
# (~1-2 coins per tick for ~50 ticks) to the next level, then sits there for thousands of ticks.
# Same shape as a TELLURIUM glide, so the same idea: once it has clearly left its plateau and is still
# moving, take 20 units in that direction and exit when the move stalls. Market-make as usual otherwise.
# Only 3 slides in 3 days (8000->7900, 7900->7800, 7800->7750), so this is a thin test; the point is
# whether the downside of false starts is small.
# Run from repo root:  python notebooks/weak/13_golden_slide.py

# %%
import itertools
import os
import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import pearls  # noqa: E402
from datamodel import Order  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "weak")
G = "GOLDEN_PEARLS"
LIMIT = 20


def take_to(depth, pos, target):
    diff, orders = target - pos, []
    if diff > 0:
        for a in sorted(depth.sell_orders):
            if diff <= 0:
                break
            q = min(diff, -depth.sell_orders[a]); orders.append(Order(G, a, q)); diff -= q
    elif diff < 0:
        for b in sorted(depth.buy_orders, reverse=True):
            if diff >= 0:
                break
            q = min(-diff, depth.buy_orders[b]); orders.append(Order(G, b, -q)); diff += q
    return orders


class GoldenSlide(pearls.Trader):
    """GOLDEN market making as in the submission, plus: if GOLDEN's mid has moved >= `move` coins over
    the last `L` ticks (it normally flickers +-0.5 around its plateau), take 20 units in that direction;
    exit when the last `K`-tick move is below `flat` coins."""

    def __init__(self, move=5, L=5, K=10, flat=1.0, mm=True):
        super().__init__({G: pearls.PARAMS[G]} if mm else {})
        self.move, self.L, self.K, self.flat = move, L, K, flat
        self.hist = deque(maxlen=max(L, K) + 1)
        self.side = 0
        self.events = []

    def run(self, state):
        d = state.order_depths[G]
        mid = (max(d.buy_orders) + min(d.sell_orders)) / 2
        self.hist.append(mid)
        pos = state.position.get(G, 0)
        h = list(self.hist)
        if self.side != 0:
            recent = mid - h[-self.K - 1] if len(h) > self.K else 0.0
            if self.side * recent < self.flat:
                self.side = 0
                self.events.append(("exit", state.timestamp // 100, mid))
                return {G: take_to(d, pos, 0)}, 0, ""
            return {G: take_to(d, pos, self.side * LIMIT)}, 0, ""
        if len(h) > self.L and abs(h[-1] - h[-1 - self.L]) >= self.move:
            self.side = 1 if h[-1] > h[-1 - self.L] else -1
            self.events.append(("enter", state.timestamp // 100, mid))
            return {G: take_to(d, pos, self.side * LIMIT)}, 0, ""
        return super().run(state)


def evaluate(kw):
    traders = []

    def f():
        t = GoldenSlide(**kw); traders.append(t); return t

    res = bt.backtest(f, (-2, -1, 0), pearls.PEARLS, record_every=0)
    n = sum(1 for t in traders for e in t.events if e[0] == "enter")
    return dict(params=str(kw), entries=n, **{f"d{d.day}": d.pnl_by_product.get(G, 0.0) for d in res.days})


if __name__ == "__main__":
    jobs = [dict(move=1e9)]  # never triggers = today's GOLDEN market maker
    for move, L, K, flat in itertools.product([3, 5, 8], [5, 10], [5, 10, 20], [0.5, 1.0]):
        jobs.append(dict(move=move, L=L, K=K, flat=flat))
    with ProcessPoolExecutor() as ex:
        df = pd.DataFrame(list(ex.map(evaluate, jobs))).rename(columns={"d-2": "d_2", "d-1": "d_1"})
    df["total"] = df[["d_2", "d_1", "d0"]].sum(axis=1)
    df["min_day"] = df[["d_2", "d_1", "d0"]].min(axis=1)
    df.to_csv(os.path.join(OUT, "21_golden_slide.csv"), index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 70)
    print("first row = today's GOLDEN (no slide riding)")
    print(df.head(1).round(0).to_string(index=False))
    print(f"\n{len(df) - 1} slide settings: {int((df.iloc[1:][['d_2', 'd_1', 'd0']] > 0).all(axis=1).sum())} positive on all 3 days; "
          f"{int((df.iloc[1:].total > df.iloc[0].total).sum())} beat today's total")
    print(df.iloc[1:].sort_values("min_day", ascending=False).head(10).round(0).to_string(index=False))
    print("\nworst 3:")
    print(df.iloc[1:].sort_values("total").head(3).round(0).to_string(index=False))
