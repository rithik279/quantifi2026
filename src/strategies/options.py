"""LYCHEE vouchers: market making around a Black-Scholes fair value, delta-hedged with LYCHEE.

Findings (notebooks/options/NOTES.md):
  - Each strike's implied vol is stable within a day; its price wanders ~+-5 coins off that and
    ~30% of the gap closes within 50 ticks (residual autocorr ~0.5 at 100 ticks).
  - So fair value = BS(S_now, K, T, slow EMA of that strike's own implied vol). It follows LYCHEE
    instantly through S, but treats short-lived IV moves as noise to fade.
  - Vouchers trade ~560 times a day each, always at the touch, so joining the touch fills a lot.
  - Net option delta is hedged with LYCHEE (limit 200).

Time to expiry: 8 days at the start of day -2, so 5 days at the start of scoring day 1.
The engine never tells us the day; DAY defaults to 1, and the local backtester calls set_day().
"""

import json
import math
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = {f"VOUCHER_{k}": k for k in STRIKES}
UNDERLYING = "LYCHEE"
LIMITS = {UNDERLYING: 200, **{v: 50 for v in VOUCHERS}}
EXPIRY_DAYS_AT_DAY_MINUS_2 = 8

# Chosen from notebooks/options/03_param_sweep.py (worst training day, checked on day 0).
PARAMS = dict(
    iv_span=1000,     # ticks: EMA span of each strike's implied vol (50 loses badly, 1000 best)
    take_edge=4.0,    # take a voucher level this far through fair
    make_edge=0.5,    # never quote closer than this to fair
    skew=1.0,         # coins of fair shift at full position
    soft_cap=50,      # max |position| per voucher
    hedge=True,       # wide band: a tight band (10) just pays LYCHEE's spread; see NOTES.md
    hedge_band=60,    # rebalance LYCHEE when |target - position| exceeds this (cuts mean |delta| 101 -> 35)
    min_price=3.0,    # skip vouchers cheaper than this (tick size dominates)
    take_mode="scaled",  # take threshold = max(take_min, take_k x recent std of (price - fair)); "fixed" = take_edge
    take_k=0.8,
    take_min=2.0,
    resid_span=1000,  # ticks: EMA span for the variance of (price - fair) per voucher
)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, sig: float) -> float:
    if T <= 0 or sig <= 0:
        return max(S - K, 0.0)
    sq = sig * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sq * sq) / sq
    return S * _ncdf(d1) - K * _ncdf(d1 - sq)


def bs_delta(S: float, K: float, T: float, sig: float) -> float:
    if T <= 0 or sig <= 0:
        return 1.0 if S > K else 0.0
    sq = sig * math.sqrt(T)
    return _ncdf((math.log(S / K) + 0.5 * sq * sq) / sq)


def implied_vol(price: float, S: float, K: float, T: float, guess: float = 0.02) -> float:
    """Bisection on [1e-4, 0.2] (vol per sqrt(day)). Returns None outside no-arbitrage bounds."""
    if price <= max(S - K, 0.0) + 1e-6 or price >= S:
        return None
    lo, hi = 1e-4, 0.2
    for _ in range(40):
        m = 0.5 * (lo + hi)
        if bs_call(S, K, T, m) > price:
            hi = m
        else:
            lo = m
    return 0.5 * (lo + hi)


class Trader:
    DAY = 1  # scoring day

    def __init__(self, params: dict = None):
        self.params = dict(PARAMS, **(params or {}))
        self.day = self.DAY

    def set_day(self, day: int):
        self.day = day

    def tte(self, timestamp: int) -> float:
        return EXPIRY_DAYS_AT_DAY_MINUS_2 - (self.day + 2) - timestamp / 1_000_000

    def quote(self, product: str, depth: OrderDepth, position: int, fair: float, take_edge: float) -> List[Order]:
        prm = self.params
        limit = LIMITS[product]
        cap = min(limit, prm["soft_cap"])
        fair_adj = fair - prm["skew"] * position / limit
        buy_cap, sell_cap = max(0, cap - position), max(0, cap + position)
        orders: List[Order] = []
        for ask in sorted(depth.sell_orders):
            if buy_cap <= 0 or ask > fair_adj - take_edge:
                break
            q = min(buy_cap, -depth.sell_orders[ask])
            orders.append(Order(product, ask, q)); buy_cap -= q
        for bid in sorted(depth.buy_orders, reverse=True):
            if sell_cap <= 0 or bid < fair_adj + take_edge:
                break
            q = min(sell_cap, depth.buy_orders[bid])
            orders.append(Order(product, bid, -q)); sell_cap -= q
        best_bid, best_ask = max(depth.buy_orders), min(depth.sell_orders)
        bid_px = int(min(best_bid, fair_adj - prm["make_edge"]) // 1)
        ask_px = int(-((-max(best_ask, fair_adj + prm["make_edge"])) // 1))
        if buy_cap > 0:
            orders.append(Order(product, bid_px, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -sell_cap))
        return orders

    def run(self, state: TradingState):
        prm = self.params
        mem = json.loads(state.traderData) if state.traderData else {}
        ivs = mem.setdefault("iv", {})
        result: Dict[str, List[Order]] = {}

        und = state.order_depths.get(UNDERLYING)
        if und is None or not und.buy_orders or not und.sell_orders:
            return result, 0, json.dumps(mem)
        S = (max(und.buy_orders) + min(und.sell_orders)) / 2
        T = self.tte(state.timestamp)
        alpha = 2 / (prm["iv_span"] + 1)

        net_delta = 0.0
        for product, K in VOUCHERS.items():
            depth = state.order_depths.get(product)
            pos = state.position.get(product, 0)
            if depth is None or not depth.buy_orders or not depth.sell_orders:
                continue
            vmid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            iv_now = implied_vol(vmid, S, K, T)
            iv = ivs.get(product)
            if iv_now is not None:
                iv = iv_now if iv is None else alpha * iv_now + (1 - alpha) * iv
                ivs[product] = iv
            if iv is None:
                continue
            net_delta += pos * bs_delta(S, K, T, iv)
            if vmid < prm["min_price"]:
                continue
            fair = bs_call(S, K, T, iv)
            take = prm["take_edge"]
            if prm["take_mode"] == "scaled":
                # how big are this voucher's wobbles right now? take only the unusually large ones
                rv = mem.setdefault("rv", {})
                resid = vmid - fair
                a = 2 / (prm["resid_span"] + 1)
                rv[product] = a * resid * resid + (1 - a) * rv.get(product, resid * resid)
                take = max(prm["take_min"], prm["take_k"] * math.sqrt(rv[product]))
            result[product] = self.quote(product, depth, pos, fair, take)

        if prm["hedge"]:
            pos_u = state.position.get(UNDERLYING, 0)
            target = max(-LIMITS[UNDERLYING], min(LIMITS[UNDERLYING], -round(net_delta)))
            diff = target - pos_u
            if abs(diff) > prm["hedge_band"]:
                if diff > 0:
                    result[UNDERLYING] = [Order(UNDERLYING, min(und.sell_orders), diff)]
                else:
                    result[UNDERLYING] = [Order(UNDERLYING, max(und.buy_orders), diff)]

        return result, 0, json.dumps(mem)
