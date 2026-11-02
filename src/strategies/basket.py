"""FRUIT_BASKET and its components (basket ~ 2D + 3G + 1M).

Owner: (fill in). First version 2026-10-28; see notebooks/basket/NOTES.md.

Rules for this file (it is pasted into the single submission file):
- Import only the standard library, `datamodel` and `strategies.common`.
- Keep module-level names unique across all strategy files (prefix them).
- Only trade the products in `products`.

Model (days -2..0): no basket-vs-components trade. The basket does move with
2D + 3G + 1M tick to tick (same-tick correlation 0.79, change weights
1.8 / 2.6 / 0.9), but the gap between them is a random walk (day -2: basket
+1,708 vs parts +119), its distance from a rolling mean doesn't close, and
neither side leads the other (all lag-1 cross-correlations < 0.013). So each
product is market-made on its own around an EMA of its mid, with small sizes.
"""

from typing import Dict, List

from datamodel import Order, TradingState
from strategies.common import market_make, mid_price

# For `market_make` (common.py); alpha is the EMA weight on the newest mid.
# A product trades only if its setting made money over days -2..0 under both
# the official and the strict fill rule.
BASKET_PARAMS = {
    # +6.2k official / +6.0k strict, but almost all on day -2 (+8.4k).
    "FRUIT_BASKET": {"alpha": 0.3, "take": 1e9, "make": 3, "skew": 0.3, "cap": 10},
    # Positive on every day: +2.8k / +3.3k.
    "DRAGONFRUIT": {"alpha": 0.3, "take": 6, "make": 1, "skew": 0.0, "cap": 10},
    # No setting beat ~0 (best: -48 official / +404 strict). Off.
    "GRANADILLA": {"alpha": 0.3, "take": 1e9, "make": 1, "skew": 0.3, "cap": 0},
    # Small: +982 / +820.
    "MANGOSTEEN": {"alpha": 0.3, "take": 6, "make": 3, "skew": 0.1, "cap": 10},
}


class BasketStrategy:
    name = "basket"
    products = ["FRUIT_BASKET", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"]

    def run(self, state: TradingState, mem: dict) -> Dict[str, List[Order]]:
        result: Dict[str, List[Order]] = {}
        emas = mem.setdefault("ema", {})
        for product, params in BASKET_PARAMS.items():
            if params["cap"] == 0:
                continue
            depth = state.order_depths.get(product)
            mid = mid_price(depth) if depth is not None else None
            if mid is None:
                continue
            ema = emas.get(product, mid)
            ema += params["alpha"] * (mid - ema)
            emas[product] = ema
            result[product] = market_make(product, depth, state.position.get(product, 0), ema, params)
        return result
