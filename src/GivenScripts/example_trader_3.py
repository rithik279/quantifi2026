from typing import Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, TradingState


class Product:
    AMETHYST = "AMETHYST"


PARAMS: Dict[str, Dict[str, int]] = {
    Product.AMETHYST: {
        "position_limit": 50,
        "fair_value": 10_000,  # We know AMETHYST has a constant fair value of 10,000
        "min_edge": 1,  # Minimum distance between each quote and fair value that we should take a trade on
        "quote_improvement": 0,  # Ticks inside the best quote; 0 means join it.
        "order_size": 100,  # Maximum size per side, still capped by position capacity.
    }
}


class Trader:
    def __init__(self, params: Optional[Dict[str, Dict[str, int]]] = None):
        self.params = params if params is not None else PARAMS

    # =========================
    # Basic helpers
    # =========================
    def get_position(self, state: TradingState, product: str) -> int:
        return state.position.get(product, 0)

    def max_buy_capacity(
        self, product: str, position: int, buy_order_volume: int = 0
    ) -> int:
        return self.params[product]["position_limit"] - position - buy_order_volume

    def max_sell_capacity(
        self, product: str, position: int, sell_order_volume: int = 0
    ) -> int:
        return self.params[product]["position_limit"] + position - sell_order_volume

    def best_ask(self, order_depth: OrderDepth) -> Optional[int]:
        return min(order_depth.sell_orders) if order_depth.sell_orders else None

    def best_bid(self, order_depth: OrderDepth) -> Optional[int]:
        return max(order_depth.buy_orders) if order_depth.buy_orders else None

    def get_mid_price(self, order_depth: OrderDepth) -> Optional[float]:
        best_bid = self.best_bid(order_depth)
        best_ask = self.best_ask(order_depth)

        if best_bid is None or best_ask is None:
            return None

        return (best_bid + best_ask) / 2

    # =========================
    # Strategy for trading AMETHYST
    # =========================
    def make_amethyst_orders(
        self,
        order_depth: OrderDepth,
        position: int,
    ) -> List[Order]:
        orders: List[Order] = []

        # get parameters for the current product 
        params = self.params[Product.AMETHYST]
        fair_value = params["fair_value"]
        min_edge = params["min_edge"]
        improvement = params["quote_improvement"]
        order_size = params["order_size"]

        # find how much we're able to buy/sell
        buy_quantity = min(order_size, self.max_buy_capacity(Product.AMETHYST, position))
        sell_quantity = min(order_size, self.max_sell_capacity(Product.AMETHYST, position))
        
        # use helper functions to determine best prices on both sides of the book
        best_bid = self.best_bid(order_depth)
        best_ask = self.best_ask(order_depth)

        # Improve the market quote only as far as our minimum edge allows.
        if best_bid is not None and buy_quantity > 0:
            bid_price = min(best_bid + improvement, fair_value - min_edge)
            orders.append(Order(Product.AMETHYST, bid_price, buy_quantity))

        if best_ask is not None and sell_quantity > 0:
            ask_price = max(best_ask - improvement, fair_value + min_edge)
            orders.append(Order(Product.AMETHYST, ask_price, -sell_quantity))

        return orders

    # =========================
    # Main
    # =========================
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}
        product = Product.AMETHYST

        if product in self.params and product in state.order_depths:
            result[product] = self.make_amethyst_orders(
                order_depth=state.order_depths[product],
                position=self.get_position(state, product),
            )

        return result, 0, ""
