"""AMETHYST starter with named settings and one separate strategy method."""

from datamodel import Order, OrderDepth, TradingState


class Trader:
    PRODUCT = "AMETHYST"
    POSITION_LIMIT = 50
    FAIR_VALUE = 10_000
    MIN_EDGE = 1
    ORDER_SIZE = 100

    def make_orders(self, book: OrderDepth, position: int) -> list[Order]:
        orders: list[Order] = []

        # Size each side independently: either side might fill on its own.
        buy_quantity = min(self.ORDER_SIZE, self.POSITION_LIMIT - position)
        sell_quantity = min(self.ORDER_SIZE, self.POSITION_LIMIT + position)

        # Join the best bid, but never pay more than fair value minus our edge.
        if book.buy_orders and buy_quantity > 0:
            best_bid = max(book.buy_orders)
            bid_price = min(best_bid, self.FAIR_VALUE - self.MIN_EDGE)
            orders.append(Order(self.PRODUCT, bid_price, buy_quantity))

        # Sell quantities are negative; keep the ask above fair value.
        if book.sell_orders and sell_quantity > 0:
            best_ask = min(book.sell_orders)
            ask_price = max(best_ask, self.FAIR_VALUE + self.MIN_EDGE)
            orders.append(Order(self.PRODUCT, ask_price, -sell_quantity))

        return orders

    def run(
        self, state: TradingState
    ) -> tuple[dict[str, list[Order]], int, str]:
        result: dict[str, list[Order]] = {}
        book = state.order_depths.get(self.PRODUCT)

        if book is not None:
            position = state.position.get(self.PRODUCT, 0)
            result[self.PRODUCT] = self.make_orders(book, position)

        # No conversions or saved state are needed for this strategy.
        return result, 0, ""
