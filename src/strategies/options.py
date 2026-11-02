"""LYCHEE and its call vouchers.

Owner: (fill in). First version 2026-10-28; see notebooks/options/NOTES.md.

Rules for this file (it is pasted into the single submission file):
- Import only the standard library, `datamodel` and `strategies.common`.
- Keep module-level names unique across all strategy files (prefix them).
- Only trade the products in `products`.

Model (days -2..0):
- Each voucher is priced by Black-Scholes (r = 0) off the LYCHEE mid. Its vol
  comes from ONE smile curve fitted across all strikes every tick (implied
  vol as a quadratic in moneyness ln(K/S)/sqrt(T)), smoothed over ~50 ticks.
  Using every strike's price to set each one's vol beat a separate smoothed
  vol per strike on every day under both fill rules (+51k over days -2..0).
- We buy or sell vouchers priced 3+ from fair value and otherwise quote inside
  the spread, letting the passive flow (~1,700 trades/strike) come to us.
- Net voucher delta is hedged with LYCHEE when it drifts past a band.
- Time to expiry: the trader can't see the day, so we assume scoring day 1
  (5 days left at its start). In backtests on days -2..0 the implied vols
  absorb the error, because fair value uses the same T they were fitted with.
"""

import math
from typing import Dict, List, Optional

from datamodel import Order, TradingState
from strategies.common import VOUCHER_STRIKES, OrderSet, best_ask, best_bid, market_make, mid_price

OPTIONS_UNDERLYING = "LYCHEE"
OPTIONS_DAYS_AT_START = 5.0  # 8 days at the start of day -2, so 5 at the start of day 1
OPTIONS_SMILE_ALPHA = 0.02  # EMA weight on each tick's fitted smile (~50-tick memory)
OPTIONS_PARAMS = {"take": 3, "make": 1, "skew": 0.0, "cap": 50}  # for market_make
OPTIONS_HEDGE_BAND = 150  # re-hedge when net delta is this far from the LYCHEE position
# A product trades only if it made money over days -2..0 under both fill rules.
# 6800 (deep in the money, little time value) lost on days -2 and -1 and only
# recovered on day 0 when implied vol jumped ~10%, so it's off.
OPTIONS_STRIKE_CAPS = {6800: 0}


def options_norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def options_call(S: float, K: float, T: float, sigma: float):
    """Black-Scholes call with r = 0. T in days, sigma per sqrt(day). Returns (price, delta, vega)."""
    sd = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sd * sd) / sd
    price = S * options_norm_cdf(d1) - K * options_norm_cdf(d1 - sd)
    vega = S * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi) * math.sqrt(T)
    return price, options_norm_cdf(d1), vega


def options_implied_vol(price: float, S: float, K: float, T: float, guess: float) -> Optional[float]:
    """Newton's method from `guess`. None when the price carries no usable time value."""
    if price <= max(S - K, 0.0) + 0.5:
        return None
    sigma = guess
    for _ in range(8):
        model, _, vega = options_call(S, K, T, sigma)
        if vega < 1e-6:
            return None
        step = (model - price) / vega
        sigma = min(max(sigma - step, 0.002), 0.2)
        if abs(step) < 1e-7:
            break
    return sigma


def options_det3(M: List[List[float]]) -> float:
    return (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1])
            - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
            + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))


def options_fit_smile(xs: List[float], ys: List[float]) -> Optional[List[float]]:
    """Least-squares y = a + b*x + c*x^2 (normal equations, Cramer's rule). None if under-determined."""
    if len(xs) < 3:
        return None
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum(y * x ** k for x, y in zip(xs, ys)) for k in range(3)]
    A = [[s[i + j] for j in range(3)] for i in range(3)]
    D = options_det3(A)
    if abs(D) < 1e-12:
        return None
    coef = []
    for c in range(3):
        M = [row[:] for row in A]
        for r in range(3):
            M[r][c] = t[r]
        coef.append(options_det3(M) / D)
    return coef


class OptionsStrategy:
    name = "options"
    products = [OPTIONS_UNDERLYING] + [f"VOUCHER_{k}" for k in VOUCHER_STRIKES]

    def run(self, state: TradingState, mem: dict) -> Dict[str, List[Order]]:
        depths = state.order_depths
        if OPTIONS_UNDERLYING not in depths:
            return {}
        S = mid_price(depths[OPTIONS_UNDERLYING])
        if S is None:
            return {}
        T = max(OPTIONS_DAYS_AT_START - state.timestamp / 1_000_000, 0.05)
        guesses = mem.setdefault("iv", {})  # last implied vol per strike, Newton's starting point

        def moneyness(K: float) -> float:
            return 100 * math.log(K / S) / math.sqrt(T)

        # 1) Implied vol of every voucher with usable time value.
        raw: Dict[int, float] = {}
        for K in VOUCHER_STRIKES:
            symbol = f"VOUCHER_{K}"
            C = mid_price(depths[symbol]) if symbol in depths else None
            if C is None:
                continue
            iv = options_implied_vol(C, S, K, T, guesses.get(str(K), 0.02))
            if iv is not None:
                raw[K] = iv
                guesses[str(K)] = iv

        # 2) One smile across strikes, smoothed over time.
        coef = options_fit_smile([moneyness(K) for K in raw], [raw[K] for K in raw])
        smile = mem.get("smile")
        if coef is not None:
            smile = coef if smile is None else [a + OPTIONS_SMILE_ALPHA * (c - a) for a, c in zip(smile, coef)]
            mem["smile"] = smile
        if smile is None:
            return {}

        # 3) Price each voucher off the smile and quote around it.
        result: Dict[str, List[Order]] = {}
        net_delta = 0.0
        for K in VOUCHER_STRIKES:
            symbol = f"VOUCHER_{K}"
            if symbol not in depths:
                continue
            x = moneyness(K)
            vol = min(max(smile[0] + smile[1] * x + smile[2] * x * x, 0.002), 0.2)
            fair, delta, _ = options_call(S, K, T, vol)
            position = state.position.get(symbol, 0)
            net_delta += position * delta
            params = dict(OPTIONS_PARAMS, cap=OPTIONS_STRIKE_CAPS.get(K, OPTIONS_PARAMS["cap"]))
            result[symbol] = market_make(symbol, depths[symbol], position, fair, params)

        result[OPTIONS_UNDERLYING] = self.hedge(depths[OPTIONS_UNDERLYING], state.position.get(OPTIONS_UNDERLYING, 0), net_delta)
        return result

    def hedge(self, depth, position: int, net_delta: float) -> List[Order]:
        """Cross the LYCHEE book to bring position back to -net_delta when it drifts past the band."""
        o = OrderSet(OPTIONS_UNDERLYING, position)
        gap = -round(net_delta) - position
        if abs(gap) <= OPTIONS_HEDGE_BAND:
            return []
        if gap > 0:
            for price in sorted(depth.sell_orders):
                if gap <= 0:
                    break
                gap -= o.buy(price, min(gap, -depth.sell_orders[price]))
        else:
            for price in sorted(depth.buy_orders, reverse=True):
                if gap >= 0:
                    break
                gap += o.sell(price, min(-gap, depth.buy_orders[price]))
        return o.orders
