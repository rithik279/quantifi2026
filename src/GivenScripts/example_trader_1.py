from datamodel import Order, TradingState


class Trader:
    def run(self, state: TradingState):
        orders = []
        book = state.order_depths.get("AMETHYST")
        position = state.position.get("AMETHYST", 0)

        # Join the best bid and ask, keeping our position between -50 and 50.
        if book is not None:
            if book.buy_orders and position < 50:
                best_bid = max(book.buy_orders)
                orders.append(Order("AMETHYST", best_bid, 50 - position))

            if book.sell_orders and position > -50:
                best_ask = min(book.sell_orders)
                orders.append(Order("AMETHYST", best_ask, -50 - position))

        return {"AMETHYST": orders}, 0, ""
