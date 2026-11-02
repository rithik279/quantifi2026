"""The five pearls (prices sum to ~50,000).

Owner: (fill in). First version 2026-10-28; see notebooks/pearls/NOTES.md.

Rules for this file (it is pasted into the single submission file):
- Import only the standard library, `datamodel` and `strategies.common`.
- Keep module-level names unique across all strategy files (prefix them).
- Only trade the products in `products`.

Model (days -2..0, see notebooks/pearls/NOTES.md):
- The five mids sum to 50,000 (std 5). When the sum drifts, PINK alone pulls
  it back: over 100 ticks PINK moves -0.8 to -0.95x the gap, the others ~0.
  So PINK's fair value is 50,000 minus the other four.
- GOLDEN's tick-to-tick mid changes have -0.42 autocorrelation (bounce), so its
  fair value is a smoothed mid.
- WHITE, BLACK, BLUE look like random walks: fair value is the mid.
- Trades print only at the best bid/ask, so quoting one tick inside fills
  even under the strict fill rule.
"""

from typing import Dict, List

from datamodel import Order, TradingState
from strategies.common import market_make, mid_price

PEARLS_TOTAL = 50_000
PEARLS_CORRECTOR = "PINK_PEARLS"
PEARLS_GOLDEN_ALPHA = 0.3  # EMA weight on the newest GOLDEN mid
# Params are for `market_make` in common.py (take / make / skew / cap).
#
# PINK: take 3-5 with no skew all give +8-9.6k per day (days -2..0), so 4 sits
# mid-plateau. Skew hurts (0.1: -10%, 0.3: -25% or worse): the mispricing takes
# ~100 ticks to close, and leaning against inventory exits before it does.
# Others: random walks. A product trades only if its setting made money over
# days -2..0 under both fill rules. At cap 3 only WHITE passes (+1,105 / +1,298,
# mostly day -1); BLACK, GOLDEN and BLUE lost at every cap (3, 5, 10, 20).
PEARLS_PARAMS = {
    "WHITE_PEARLS": {"take": 3, "make": 1, "skew": 0.1, "cap": 3},
    "BLACK_PEARLS": {"take": 3, "make": 1, "skew": 0.1, "cap": 0},
    "GOLDEN_PEARLS": {"take": 3, "make": 1, "skew": 0.1, "cap": 0},
    "PINK_PEARLS": {"take": 4, "make": 1, "skew": 0.0, "cap": 20},
    "BLUE_PEARLS": {"take": 3, "make": 1, "skew": 0.1, "cap": 0},
}


class PearlsStrategy:
    name = "pearls"
    products = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]

    def run(self, state: TradingState, mem: dict) -> Dict[str, List[Order]]:
        depths = state.order_depths
        if any(p not in depths for p in self.products):
            return {}
        mids = {p: mid_price(depths[p]) for p in self.products}
        if any(m is None for m in mids.values()):
            return {}

        fair = dict(mids)
        fair[PEARLS_CORRECTOR] = PEARLS_TOTAL - sum(m for p, m in mids.items() if p != PEARLS_CORRECTOR)
        golden = mem.get("golden_ema", mids["GOLDEN_PEARLS"])
        golden += PEARLS_GOLDEN_ALPHA * (mids["GOLDEN_PEARLS"] - golden)
        mem["golden_ema"] = golden
        fair["GOLDEN_PEARLS"] = golden

        return {
            p: market_make(p, depths[p], state.position.get(p, 0), fair[p], PEARLS_PARAMS[p])
            for p in self.products
        }
