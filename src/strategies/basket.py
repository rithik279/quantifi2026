"""FRUIT_BASKET vs 2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN.

Findings (notebooks/basket/NOTES.md):
  - Weights 2/3/1 (regressions on price changes at 10..500 ticks: 1.9-2.0 / 3.0 / 0.8-1.0).
  - premium = basket - NAV is NOT anchored to a rolling mean (signals flip sign day to day), but it
    is pulled slowly toward a fixed level near 0..60 (slope -0.5 over 3,000 ticks).
  - Basket and fruits trade only ~16-25 times a day, so this strategy TAKES liquidity.

Strategy: hold a basket position proportional to how far the premium is from the anchor,
    target = -clip((premium - anchor) / scale, -1, 1) * max_baskets
and optionally hedge each basket with -2 D, -3 G, -1 M so only the premium is held.
"""

import json
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

BASKET = "FRUIT_BASKET"
WEIGHTS = {"DRAGONFRUIT": 2, "GRANADILLA": 3, "MANGOSTEEN": 1}
LIMITS = {BASKET: 40, "DRAGONFRUIT": 40, "GRANADILLA": 40, "MANGOSTEEN": 40}

PARAMS = dict(
    anchor=0.0,        # premium level the spread is pulled toward
    scale=1000.0,      # premium deviation at which we hold the full position
    max_baskets=40,    # 40 unhedged; hedged is capped at 13 by GRANADILLA's limit (3 x 13 = 39)
    hedge=True,
    min_trade=4,       # don't rebalance for less than this many baskets (1 over-trades and loses every day)
)


def _mid(d: OrderDepth) -> float:
    return (max(d.buy_orders) + min(d.sell_orders)) / 2


def _move_to(product: str, depth: OrderDepth, position: int, target: int, limit: int) -> List[Order]:
    """Cross the book toward `target`, never past the position limit."""
    target = max(-limit, min(limit, target))
    diff = target - position
    orders: List[Order] = []
    if diff > 0:
        for ask in sorted(depth.sell_orders):
            if diff <= 0:
                break
            q = min(diff, -depth.sell_orders[ask])
            orders.append(Order(product, ask, q)); diff -= q
    elif diff < 0:
        for bid in sorted(depth.buy_orders, reverse=True):
            if diff >= 0:
                break
            q = min(-diff, depth.buy_orders[bid])
            orders.append(Order(product, bid, -q)); diff += q
    return orders


class Trader:
    def __init__(self, params: dict = None):
        self.params = dict(PARAMS, **(params or {}))

    def run(self, state: TradingState):
        prm = self.params
        names = [BASKET] + list(WEIGHTS)
        depths = {p: state.order_depths.get(p) for p in names}
        if any(d is None or not d.buy_orders or not d.sell_orders for d in depths.values()):
            return {}, 0, state.traderData
        mids = {p: _mid(d) for p, d in depths.items()}
        premium = mids[BASKET] - sum(w * mids[p] for p, w in WEIGHTS.items())

        max_b = prm["max_baskets"]
        if prm["hedge"]:
            max_b = min(max_b, min(LIMITS[p] // w for p, w in WEIGHTS.items()))
        dev = (premium - prm["anchor"]) / prm["scale"]
        target = int(round(-max(-1.0, min(1.0, dev)) * max_b))

        pos_b = state.position.get(BASKET, 0)
        result: Dict[str, List[Order]] = {}
        if abs(target - pos_b) >= prm["min_trade"]:
            result[BASKET] = _move_to(BASKET, depths[BASKET], pos_b, target, LIMITS[BASKET])
        if prm["hedge"]:
            # hedge the basket position we actually hold (fills come next tick)
            for p, w in WEIGHTS.items():
                tgt = -w * pos_b
                pos = state.position.get(p, 0)
                if tgt != pos:
                    result[p] = _move_to(p, depths[p], pos, tgt, LIMITS[p])
        return result, 0, json.dumps({"premium": premium})
