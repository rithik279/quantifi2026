"""Pearls: market making with structure-aware fair values.

Findings (notebooks/pearls/NOTES.md):
  - The five pearl mids sum to 50,000 (std 5). PINK is the one that closes the gap:
    its future move ~ -k * (sum - 50,000), with k ~ 0.4 at 20 ticks, ~0.7 at 50, ~1.0 at 200.
  - GOLDEN sits on plateaus (8000 / 7900 / 7800 / 7750) with +-0.5 quote noise.
  - Every trade prints at or through the touch, so we join the touch (see standalone notes).
"""

import json
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
LIMITS = {p: 20 for p in PEARLS}
SUM_TARGET = 50_000

# fair: "mid" | "plateau" (round to nearest `step` when within `snap`) | "sum" (mid - k * sum deviation)
# Chosen from notebooks/pearls/02_param_sweep.py (worst training day, then checked on day 0).
# WHITE/BLACK/BLUE have no edge yet; small soft_cap keeps them in the book for breadth at low risk.
PARAMS: Dict[str, dict] = {
    "WHITE_PEARLS":  dict(fair="mid", take_edge=100, make_edge=2, skew=0, soft_cap=5),
    "BLACK_PEARLS":  dict(fair="mid", take_edge=100, make_edge=3, skew=5, soft_cap=5),
    "GOLDEN_PEARLS": dict(fair="plateau", step=50, snap=0.5, take_edge=2, make_edge=0.5, skew=5, soft_cap=20),
    "PINK_PEARLS":   dict(fair="sum", k=0.5, take_edge=1, make_edge=0.5, skew=0, soft_cap=20),
    "BLUE_PEARLS":   dict(fair="mid", take_edge=100, make_edge=3, skew=2, soft_cap=5),
}


def _mid(depth: OrderDepth) -> float:
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2


class Trader:
    def __init__(self, params: Dict[str, dict] = None):
        self.params = params if params is not None else PARAMS

    def fair_value(self, product: str, mids: Dict[str, float]) -> float:
        prm = self.params[product]
        mid = mids[product]
        if prm["fair"] == "plateau":
            level = round(mid / prm["step"]) * prm["step"]
            return level if abs(mid - level) <= prm["snap"] else mid
        if prm["fair"] == "sum" and len(mids) == len(PEARLS):
            dev = sum(mids.values()) - SUM_TARGET
            return mid - prm["k"] * dev
        return mid

    def make_orders(self, product: str, depth: OrderDepth, position: int, fair: float) -> List[Order]:
        prm = self.params[product]
        limit = LIMITS[product]
        orders: List[Order] = []
        fair_adj = fair - prm["skew"] * position / limit
        cap = min(limit, prm.get("soft_cap", limit))  # stop adding inventory beyond this size
        buy_cap, sell_cap = max(0, cap - position), max(0, cap + position)

        for ask in sorted(depth.sell_orders):
            if buy_cap <= 0 or ask > fair_adj - prm["take_edge"]:
                break
            q = min(buy_cap, -depth.sell_orders[ask])
            orders.append(Order(product, ask, q))
            buy_cap -= q
        for bid in sorted(depth.buy_orders, reverse=True):
            if sell_cap <= 0 or bid < fair_adj + prm["take_edge"]:
                break
            q = min(sell_cap, depth.buy_orders[bid])
            orders.append(Order(product, bid, -q))
            sell_cap -= q

        best_bid, best_ask = max(depth.buy_orders), min(depth.sell_orders)
        bid_px = int(min(best_bid, fair_adj - prm["make_edge"]) // 1)
        ask_px = int(-((-max(best_ask, fair_adj + prm["make_edge"])) // 1))
        if buy_cap > 0:
            orders.append(Order(product, bid_px, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -sell_cap))
        return orders

    def run(self, state: TradingState):
        depths = {p: state.order_depths[p] for p in PEARLS
                  if p in state.order_depths and state.order_depths[p].buy_orders and state.order_depths[p].sell_orders}
        mids = {p: _mid(d) for p, d in depths.items()}
        result = {}
        for product in self.params:
            if product not in depths:
                continue
            fair = self.fair_value(product, mids)
            result[product] = self.make_orders(product, depths[product], state.position.get(product, 0), fair)
        return result, 0, ""
