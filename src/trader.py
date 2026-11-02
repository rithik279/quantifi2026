"""Development entry point: routes each product group to its strategy.

Don't upload this file directly. Run `python src/build_submission.py` to paste
it together with `strategies/*.py` into `submission/trader.py`.

traderData is one JSON object with a slice per strategy, e.g.
{"pearls": {...}, "options": {...}}, so strategies can't overwrite each other.
"""

import json
import sys
import traceback
from typing import Dict, List

from datamodel import Order, TradingState
from strategies.basket import BasketStrategy
from strategies.common import clip_to_limit
from strategies.options import OptionsStrategy
from strategies.pearls import PearlsStrategy
from strategies.standalone import StandaloneStrategy


class Trader:
    def __init__(self):
        self.strategies = [
            StandaloneStrategy(),
            BasketStrategy(),
            OptionsStrategy(),
            PearlsStrategy(),
        ]
        self.reported = set()
        seen: Dict[str, str] = {}
        for s in self.strategies:
            for p in s.products:
                if p in seen:
                    raise ValueError(f"{p} is claimed by both {seen[p]} and {s.name}")
                seen[p] = s.name

    def report_once(self, key: str, message: str) -> None:
        # stderr, so the local backtester shows it even when it hides prints.
        if key not in self.reported:
            self.reported.add(key)
            print(message, file=sys.stderr)

    def run(self, state: TradingState):
        try:
            memory = json.loads(state.traderData) if state.traderData else {}
        except ValueError:
            memory = {}

        result: Dict[str, List[Order]] = {}
        for strategy in self.strategies:
            mem = memory.setdefault(strategy.name, {})
            try:
                orders = strategy.run(state, mem)
            except Exception:
                # One broken strategy must not stop the others from trading.
                self.report_once(strategy.name, f"[{strategy.name}] crashed:\n{traceback.format_exc()}")
                continue
            for product, product_orders in orders.items():
                if product not in strategy.products:
                    self.report_once(f"{strategy.name}:{product}",
                                     f"[{strategy.name}] ignored orders for {product}: not in its products")
                    continue
                position = state.position.get(product, 0)
                result[product] = clip_to_limit(product, product_orders, position)

        return result, 0, json.dumps(memory, separators=(",", ":"))
