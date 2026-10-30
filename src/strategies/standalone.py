"""Standalone products: one market-making engine, a different fair value per product.

Key fact from the data (notebooks/standalone/NOTES.md): every historical trade prints AT or
BEYOND the best bid/ask, never inside the spread. Under the official fill rule (passive fill if a
trade prints at our price or better) that means quoting exactly at the touch captures every trade
at the best possible price. So the engine:
  1. estimates a fair value (product-specific),
  2. takes any book level that is better than fair by >= take_edge,
  3. joins the touch on each side, but never closer to fair than make_edge,
  4. skews fair value against inventory so position mean-reverts.
"""

import json
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

LIMITS = {"AMETHYST": 50, "TOFFEE_CAKE": 50, "PAPER_LANTERNS": 50, "TELLURIUM": 40, "JELLY": 50, "PEANUT_BUTTER": 50}

# fair: "fixed" uses `value`; "ema" uses an EMA of the mid with `span`; "mid" uses the current mid;
#       "trend" = EMA + its slope over `slope_window` ticks, extrapolated `lead` ticks ahead.
# anchor/anchor_w: pull the fair value toward a long-run level (mean reversion).
# flow_beta/flow_decay: shift fair value by recent signed aggressor volume (informed flow).
# soft_cap: max |position| we build (the hard limit still applies).
# glide (TELLURIUM): after a jump of >= J coins within 5 ticks, wait W ticks; if the price has moved
#   >= gmin since the jump, take the full limit in that direction ("ride the glide") and hold until the
#   last K-tick move stalls below `flat` (or after H ticks); then flatten ("take") or hand back to market
#   making ("mm"). Market making runs whenever no glide trade is on. See notebooks/weak/NOTES.md.
# take_edge=100 effectively disables taking. Choices are explained in notebooks/standalone/NOTES.md.
GLIDE = dict(J=60, W=20, gmin=15, K=20, flat=0.0, H=300, cool=50, exit="take")
PARAMS: Dict[str, dict] = {
    "AMETHYST":       dict(fair="fixed", value=10_000, take_edge=1, make_edge=1, skew=0),
    "TOFFEE_CAKE":    dict(fair="ema", span=10, anchor=5_000, anchor_w=0.5, take_edge=8, make_edge=2, skew=0),
    "PAPER_LANTERNS": dict(fair="trend", span=20, slope_window=100, lead=100, take_edge=1, make_edge=1, skew=2),
    "TELLURIUM":      dict(fair="mid", flow_beta=0.8, flow_decay=0.9, take_edge=100, make_edge=3, skew=5, soft_cap=15,
                           glide=GLIDE),
    "JELLY":          dict(fair="mid", take_edge=100, make_edge=1, skew=0, soft_cap=3),
    "PEANUT_BUTTER":  dict(fair="mid", take_edge=100, make_edge=3, skew=5, soft_cap=10),
}


class Trader:
    def __init__(self, params: Dict[str, dict] = None):
        self.params = params if params is not None else PARAMS

    # ---------- fair value ----------
    def fair_value(self, product: str, depth: OrderDepth, state: TradingState, mem: dict) -> float:
        prm = self.params[product]
        best_bid, best_ask = max(depth.buy_orders), min(depth.sell_orders)
        mid = (best_bid + best_ask) / 2
        pm = mem.setdefault(product, {})

        if prm["fair"] == "fixed":
            fair = prm["value"]
        elif prm["fair"] in ("ema", "trend"):
            alpha = 2 / (prm["span"] + 1)
            ema = pm.get("ema", mid)
            ema = alpha * mid + (1 - alpha) * ema
            pm["ema"] = ema
            fair = ema
            if prm["fair"] == "trend":
                # PAPER_LANTERNS drifts in straight lines: extrapolate the smoothed slope `lead` ticks ahead
                hist = pm.setdefault("hist", [])
                hist.append(ema)
                if len(hist) > prm["slope_window"]:
                    hist.pop(0)
                slope = (hist[-1] - hist[0]) / max(1, len(hist) - 1)
                fair = ema + slope * prm["lead"]
        else:
            fair = mid

        if "anchor" in prm:
            fair = (1 - prm["anchor_w"]) * fair + prm["anchor_w"] * prm["anchor"]

        if "flow_beta" in prm:
            # sign last tick's market trades against last tick's mid
            prev_mid = pm.get("prev_mid", mid)
            signed = 0
            for t in state.market_trades.get(product, []):
                if t.price > prev_mid:
                    signed += t.quantity
                elif t.price < prev_mid:
                    signed -= t.quantity
            flow = pm.get("flow", 0.0) * prm["flow_decay"] + signed
            pm["flow"] = flow
            fair += prm["flow_beta"] * flow
        pm["prev_mid"] = mid
        return fair

    # ---------- order generation ----------
    def make_orders(self, product: str, depth: OrderDepth, position: int, fair: float) -> List[Order]:
        prm = self.params[product]
        limit = LIMITS[product]
        orders: List[Order] = []
        fair_adj = fair - prm["skew"] * position / limit  # long -> lower fair -> sell sooner

        # soft_cap: stop adding inventory beyond this size (random-walk products drift hard)
        cap = min(limit, prm.get("soft_cap", limit))
        buy_cap = max(0, cap - position)
        sell_cap = max(0, cap + position)

        # 1) take mispriced levels
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

        # 2) join the touch (or step `improve` ticks inside it), never closer to fair than make_edge
        best_bid, best_ask = max(depth.buy_orders), min(depth.sell_orders)
        improve = prm.get("improve", 0)
        bid_px = int(min(best_bid + improve, fair_adj - prm["make_edge"]) // 1)
        ask_px = int(-((-max(best_ask - improve, fair_adj + prm["make_edge"])) // 1))  # ceil
        if buy_cap > 0:
            orders.append(Order(product, bid_px, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -sell_cap))
        return orders

    # ---------- glide overlay (TELLURIUM) ----------
    def glide_signal(self, mid: float, pm: dict, g: dict, limit: int):
        """Returns a target position while a glide trade is on, "exit" on the tick it ends, else None.
        Uses its own tick counter, so it doesn't depend on timestamps resetting between days."""
        gs = pm.setdefault("glide", {"hist": [], "tick": 0, "jump": None, "side": 0, "t_in": 0, "last_end": -10**9})
        gs["tick"] += 1
        t = gs["tick"]
        hist = gs["hist"]
        hist.append(mid)
        if len(hist) > max(5, g["K"]) + 1:
            hist.pop(0)
        if gs["side"] != 0:
            recent = mid - hist[-g["K"] - 1] if len(hist) > g["K"] else 0.0
            if t - gs["t_in"] >= g["H"] or gs["side"] * recent < g["flat"]:
                gs["side"], gs["jump"], gs["last_end"] = 0, None, t
                return "exit"
            return gs["side"] * limit
        if len(hist) > 5 and abs(hist[-1] - hist[-6]) >= g["J"] and t - gs["last_end"] >= g["cool"]:
            gs["jump"] = [t, mid]  # a new jump restarts the clock
        if gs["jump"] is not None and t - gs["jump"][0] >= g["W"]:
            move = mid - gs["jump"][1]
            gs["jump"] = None
            if abs(move) >= g["gmin"]:
                gs["side"], gs["t_in"] = (1 if move > 0 else -1), t
                return gs["side"] * limit
        return None

    @staticmethod
    def take_to(product: str, depth: OrderDepth, position: int, target: int) -> List[Order]:
        """Cross the book level by level toward `target`."""
        diff, orders = target - position, []
        if diff > 0:
            for ask in sorted(depth.sell_orders):
                if diff <= 0:
                    break
                q = min(diff, -depth.sell_orders[ask])
                orders.append(Order(product, ask, q))
                diff -= q
        elif diff < 0:
            for bid in sorted(depth.buy_orders, reverse=True):
                if diff >= 0:
                    break
                q = min(-diff, depth.buy_orders[bid])
                orders.append(Order(product, bid, -q))
                diff += q
        return orders

    def run(self, state: TradingState):
        mem = json.loads(state.traderData) if state.traderData else {}
        result = {}
        for product in self.params:
            depth = state.order_depths.get(product)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue
            prm = self.params[product]
            position = state.position.get(product, 0)
            fair = self.fair_value(product, depth, state, mem)  # always run, so its memory stays current
            if "glide" in prm:
                mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
                sig = self.glide_signal(mid, mem[product], prm["glide"], LIMITS[product])
                if sig == "exit" and prm["glide"]["exit"] == "take":
                    result[product] = self.take_to(product, depth, position, 0)
                    continue
                if sig is not None and sig != "exit":
                    result[product] = self.take_to(product, depth, position, sig)
                    continue
            result[product] = self.make_orders(product, depth, position, fair)
        return result, 0, json.dumps(mem)
