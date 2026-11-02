"""Shared helpers every strategy can use.

This file is pasted into the single submission file by `src/build_submission.py`,
so it may only import the standard library and `datamodel`.
"""

import math
from typing import Dict, List, Optional

from datamodel import Order, OrderDepth

# Official position limits (Products PDF). Vouchers are 50 per strike.
VOUCHER_STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
LIMITS: Dict[str, int] = {
    "AMETHYST": 50,
    "TOFFEE_CAKE": 50,
    "PAPER_LANTERNS": 50,
    "TELLURIUM": 40,
    "JELLY": 50,
    "PEANUT_BUTTER": 50,
    "DRAGONFRUIT": 40,
    "GRANADILLA": 40,
    "MANGOSTEEN": 40,
    "FRUIT_BASKET": 40,
    "LYCHEE": 200,
    **{f"VOUCHER_{k}": 50 for k in VOUCHER_STRIKES},
    "WHITE_PEARLS": 20,
    "BLACK_PEARLS": 20,
    "GOLDEN_PEARLS": 20,
    "PINK_PEARLS": 20,
    "BLUE_PEARLS": 20,
}


def best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders) if depth.buy_orders else None


def best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders) if depth.sell_orders else None


def mid_price(depth: OrderDepth) -> Optional[float]:
    bid, ask = best_bid(depth), best_ask(depth)
    if bid is None or ask is None:
        return None
    return (bid + ask) / 2


def clip_to_limit(product: str, orders: List[Order], position: int) -> List[Order]:
    """Trim orders, in the order given, so all buys (and all sells) fit the limit.

    A last safety net in `Trader.run`: strategies should already size from their
    position (see `OrderSet`), but one oversized order would otherwise get every
    order for the product cancelled.
    """
    limit = LIMITS[product]
    buy_room, sell_room = limit - position, limit + position
    clipped: List[Order] = []
    for o in orders:
        if o.quantity > 0:
            q = min(o.quantity, buy_room)
            buy_room -= max(q, 0)
            if q > 0:
                clipped.append(Order(product, o.price, q))
        elif o.quantity < 0:
            q = min(-o.quantity, sell_room)
            sell_room -= max(q, 0)
            if q > 0:
                clipped.append(Order(product, o.price, -q))
    return clipped


class OrderSet:
    """Orders for one product, clipped so possible fills never break the limit.

    The exchange cancels *all* of a product's orders if the buys (or sells) could
    together push the position past the limit, so capacity is tracked per side:

        o = OrderSet("AMETHYST", state.position.get("AMETHYST", 0))
        o.buy(9998, 20)    # returns the quantity actually placed
        o.sell(10002, 20)  # pass a positive quantity; stored as negative
        result["AMETHYST"] = o.orders
    """

    def __init__(self, product: str, position: int, limit: Optional[int] = None):
        self.product = product
        self.limit = LIMITS[product] if limit is None else limit
        self.buy_capacity = self.limit - position
        self.sell_capacity = self.limit + position
        self.orders: List[Order] = []

    def buy(self, price: int, quantity: int) -> int:
        quantity = min(int(quantity), self.buy_capacity)
        if quantity > 0:
            self.orders.append(Order(self.product, int(price), quantity))
            self.buy_capacity -= quantity
            return quantity
        return 0

    def sell(self, price: int, quantity: int) -> int:
        quantity = min(int(quantity), self.sell_capacity)
        if quantity > 0:
            self.orders.append(Order(self.product, int(price), -quantity))
            self.sell_capacity -= quantity
            return quantity
        return 0


def market_make(product: str, depth: OrderDepth, position: int, fair: float, params: dict) -> List[Order]:
    """Take what's mispriced, then quote one tick inside the spread around `fair`.

    params:
      take: cross the book when it is at least this far through fair value.
      make: never quote closer to fair than this.
      skew: shift fair by -skew * position to lean against inventory.
      cap:  our own position limit (at most the official one).
    """
    o = OrderSet(product, position, limit=params["cap"])
    fair = fair - params["skew"] * position

    for price in sorted(depth.sell_orders):
        if price > fair - params["take"]:
            break
        o.buy(price, -depth.sell_orders[price])
    for price in sorted(depth.buy_orders, reverse=True):
        if price < fair + params["take"]:
            break
        o.sell(price, depth.buy_orders[price])

    bid, ask = best_bid(depth), best_ask(depth)
    if bid is None or ask is None:
        return o.orders
    bid_price = min(bid + 1, math.floor(fair - params["make"]), ask - 1)
    ask_price = max(ask - 1, math.ceil(fair + params["make"]), bid + 1)
    o.buy(bid_price, o.buy_capacity)
    o.sell(ask_price, o.sell_capacity)
    return o.orders
