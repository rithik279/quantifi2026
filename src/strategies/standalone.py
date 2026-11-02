"""Standalone products: market-make each around its own fair value.

Owner: (fill in). First version 2026-10-28; see notebooks/standalone/NOTES.md.

Rules for this file (it is pasted into the single submission file):
- Import only the standard library, `datamodel` and `strategies.common`.
- Keep module-level names unique across all strategy files (prefix them).
- Only trade the products in `products`.
"""

from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState
from strategies.common import OrderSet, market_make, mid_price

# AMETHYST is pinned at 10,000: over days -2..0 the book is always 9998/9999
# against 10001/10002, and every trade printed at one of those four prices.
AMETHYST_FAIR = 10_000

# The rest: `market_make` (common.py) around an EMA of the mid. `alpha` is the
# EMA weight on the newest mid (1 = the mid itself). Picked from a grid on days
# -2..0, preferring settings that were positive on every day and robust to
# their neighbours (notebooks/standalone/NOTES.md has the evidence).
STANDALONE_PARAMS = {
    # Mean-reverting (variance ratio 0.11 at 1,000 ticks), spread ~15.
    "TOFFEE_CAKE": {"alpha": 0.3, "take": 3, "make": 1, "skew": 0.3, "cap": 12},
    # Mid bounces (lag-1 autocorrelation -0.5), so a slow EMA is a better fair value.
    "PAPER_LANTERNS": {"alpha": 0.005, "take": 1e9, "make": 1, "skew": 0.0, "cap": 50},
    # Random walk with informed flow: quote wide, small, and lean hard against inventory.
    "TELLURIUM": {"alpha": 1.0, "take": 1e9, "make": 3, "skew": 0.3, "cap": 10},
    # Random walk; no setting was positive on every day. This one is positive
    # under both fill rules (+3.2k / +1.8k) and so are most of its neighbours.
    "JELLY": {"alpha": 0.3, "take": 6, "make": 3, "skew": 0.1, "cap": 25},
    # Random walk, spread 6: small size, lean against inventory.
    "PEANUT_BUTTER": {"alpha": 0.3, "take": 1e9, "make": 1, "skew": 0.3, "cap": 12},
}


class StandaloneStrategy:
    name = "standalone"
    products = ["AMETHYST", "TOFFEE_CAKE", "PAPER_LANTERNS", "TELLURIUM", "JELLY", "PEANUT_BUTTER"]

    def run(self, state: TradingState, mem: dict) -> Dict[str, List[Order]]:
        """Return orders for this tick.

        `mem` is this strategy's own slice of traderData. Mutate it to remember
        things between ticks; it must stay JSON-serialisable and small.
        """
        result: Dict[str, List[Order]] = {}
        if "AMETHYST" in state.order_depths:
            position = state.position.get("AMETHYST", 0)
            result["AMETHYST"] = self.amethyst(state.order_depths["AMETHYST"], position)

        emas = mem.setdefault("ema", {})
        for product, params in STANDALONE_PARAMS.items():
            depth = state.order_depths.get(product)
            mid = mid_price(depth) if depth is not None else None
            if mid is None:
                continue
            ema = emas.get(product, mid)
            ema += params["alpha"] * (mid - ema)
            emas[product] = ema
            result[product] = market_make(product, depth, state.position.get(product, 0), ema, params)
        return result

    def amethyst(self, depth: OrderDepth, position: int) -> List[Order]:
        fair = AMETHYST_FAIR
        o = OrderSet("AMETHYST", position)

        # Take anything priced through fair. Never happened on days -2..0, but
        # it's free money if day 1 has it.
        for price in sorted(depth.sell_orders):
            if price >= fair:
                break
            o.buy(price, -depth.sell_orders[price])
        for price in sorted(depth.buy_orders, reverse=True):
            if price <= fair:
                break
            o.sell(price, depth.buy_orders[price])

        # Half the size two ticks out, the rest one tick out. Trades print at
        # 9998/9999/10001/10002 only. Under the official rule the outer quote
        # earns 2 on trades at exactly 9998/10002, and under a strict rule the
        # inner quote still fills on them (days -2..0: +1,612 official, +556 strict;
        # quoting only the outer level gives 0 under the strict rule).
        o.buy(fair - 2, o.buy_capacity // 2)
        o.sell(fair + 2, o.sell_capacity // 2)
        o.buy(fair - 1, o.buy_capacity)
        o.sell(fair + 1, o.sell_capacity)
        return o.orders
