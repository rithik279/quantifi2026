"""LYCHEE vouchers priced off a volatility smile fitted across strikes (the trader_v4 options book).

How it differs from options.py (notebooks/hybrid/NOTES.md has the comparison):
  - options.py prices each strike off a slow EMA of ITS OWN implied vol. This file fits one smile
    (implied total vol as a quadratic in log-moneyness, vega-weighted) across all strikes every tick,
    smooths its three coefficients with a fast EMA, and prices every voucher off that smile.
  - So a voucher that drifts away from its neighbours is mispriced *now*. The fit borrows information
    from the other nine strikes, which is why a fast smoothing works here (span 50: 189k over three
    days), while a fast per-strike EMA loses money (-29k) and a slow smile (span 1,000) only matches
    options.py (130k).
  - It works in total volatility (sigma x sqrt(T)), so it never needs the time to expiry.
  - Relative-value positions are long some strikes and short their neighbours, so the book's net
    delta stays small (mean |delta| 39) without much LYCHEE hedging. LYCHEE is market-made with a soft
    cap of 40 and a small skew toward the hedge position; removing it changes PnL by under 1k.
"""

import json
import math
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = {f"VOUCHER_{k}": k for k in STRIKES}
UNDERLYING = "LYCHEE"
LIMITS = {UNDERLYING: 200, **{v: 50 for v in VOUCHERS}}

# smile_span : EMA span (ticks) for the smile's three coefficients
# min_points : fit only when at least this many strikes have a usable implied vol
# take       : take a voucher level at least this far through fair; edge: never quote closer than this
# skew       : fair shift (coins) at the soft cap, against inventory relative to the target
# LYCHEE     : market-made around its mid, drifting toward -hedge x book delta, soft cap max_pos
# take_scale (adaptive): track the book's wobble size, the mean |voucher mid - smile fair| over vouchers
#   worth >= 3 coins (a running mean for the first `warmup` ticks, then an EMA over ~2,000 ticks). The real
#   days stay at 2.6-3.8. Below `gate`, wobbles are clearly smaller than anything in the data, so the take
#   threshold shrinks with them: take x wobble / ref, never below `floor`. It is never raised: with 20%
#   bigger wobbles a 3-coin take was still best. None = fixed take. See notebooks/hybrid/NOTES.md.
TAKE_SCALE = dict(ref=3.15, gate=2.4, floor=2.0, warmup=1000)
PARAMS = dict(
    smile_span=50, min_points=5,
    take=3.0, edge=2.0, skew=0.0,
    lychee=dict(take=2.0, edge=1.0, skew=3.0, max_pos=40, hedge=1.0),
    take_scale=TAKE_SCALE,
)


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, v: float) -> float:
    """Black-Scholes call, zero rates, in TOTAL volatility v = sigma x sqrt(T)."""
    if v <= 1e-9:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * v * v) / v
    return S * _ncdf(d1) - K * _ncdf(d1 - v)


def bs_delta(S: float, K: float, v: float) -> float:
    if v <= 1e-9:
        return 1.0 if S > K else 0.0
    return _ncdf((math.log(S / K) + 0.5 * v * v) / v)


def implied_total_vol(price: float, S: float, K: float):
    """Bisection on total vol. None when the price carries (almost) no time value."""
    if price <= max(S - K, 0.0) + 0.25 or price >= S:
        return None
    lo, hi = 1e-4, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if bs_call(S, K, mid) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def fit_quadratic(xs: List[float], ys: List[float], ws: List[float]):
    """Weighted least squares y = a + b x + c x^2 (3x3 normal equations, Gaussian elimination)."""
    s = [0.0] * 5
    t = [0.0] * 3
    for x, y, w in zip(xs, ys, ws):
        p = 1.0
        for k in range(5):
            s[k] += w * p
            if k < 3:
                t[k] += w * p * y
            p *= x
    M = [[s[0], s[1], s[2], t[0]], [s[1], s[2], s[3], t[1]], [s[2], s[3], s[4], t[2]]]
    for i in range(3):
        piv = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[piv][i]) < 1e-12:
            return None
        M[i], M[piv] = M[piv], M[i]
        for r in range(3):
            if r != i:
                f = M[r][i] / M[i][i]
                for c in range(i, 4):
                    M[r][c] -= f * M[i][c]
    return [M[i][3] / M[i][i] for i in range(3)]


def _ema(prev, x, span):
    return x if prev is None else prev + 2.0 / (span + 1.0) * (x - prev)


def _mid(od: OrderDepth) -> float:
    return 0.5 * (max(od.buy_orders) + min(od.sell_orders))


def market_make(product: str, od: OrderDepth, position: int, fair: float, take: float, edge: float,
                skew: float, max_pos: int, target: float = 0.0) -> List[Order]:
    """Take levels at least `take` through fair, then join the touch on each side (never closer than
    `edge` to a reservation price skewed against inventory relative to `target`). Total size on each
    side never exceeds what the soft cap and the position limit allow."""
    limit = LIMITS[product]
    cap = min(limit, max_pos)
    buy_cap = max(0, min(limit - position, cap - position))
    sell_cap = max(0, min(limit + position, cap + position))
    orders: List[Order] = []
    asks = sorted(od.sell_orders.items())
    bids = sorted(od.buy_orders.items(), reverse=True)
    taken_ask, taken_bid = set(), set()
    pos_after = position
    for px, vol in asks:
        if buy_cap <= 0 or px > fair - take:
            break
        q = min(-vol, buy_cap)
        orders.append(Order(product, px, q)); buy_cap -= q; pos_after += q; taken_ask.add(px)
    for px, vol in bids:
        if sell_cap <= 0 or px < fair + take:
            break
        q = min(vol, sell_cap)
        orders.append(Order(product, px, -q)); sell_cap -= q; pos_after -= q; taken_bid.add(px)

    reservation = fair - skew * (pos_after - target) / cap
    rem_bids = [px for px, _ in bids if px not in taken_bid]
    rem_asks = [px for px, _ in asks if px not in taken_ask]
    bb = rem_bids[0] if rem_bids else math.floor(fair) - 1
    ba = rem_asks[0] if rem_asks else math.ceil(fair) + 1
    bid_px = min(bb, math.floor(reservation - edge))
    ask_px = max(ba, math.ceil(reservation + edge))
    if asks:
        bid_px = min(bid_px, asks[0][0] - 1)  # a resting quote never crosses the book
    if bids:
        ask_px = max(ask_px, bids[0][0] + 1)
    if bid_px >= ask_px:
        bid_px, ask_px = ask_px - 1, bid_px + 1
    if buy_cap > 0:
        orders.append(Order(product, int(bid_px), int(buy_cap)))
    if sell_cap > 0:
        orders.append(Order(product, int(ask_px), -int(sell_cap)))
    return orders


class Trader:
    def __init__(self, params: dict = None):
        self.params = dict(PARAMS, **(params or {}))

    def run(self, state: TradingState):
        prm = self.params
        mem = json.loads(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}
        ods = state.order_depths
        und = ods.get(UNDERLYING)
        if und is None or not und.buy_orders or not und.sell_orders:
            return result, 0, json.dumps(mem)
        S = _mid(und)

        # 1) implied total vol for every voucher with a usable price, weighted by vega
        xs, ys, ws, info = [], [], [], {}
        for sym, K in VOUCHERS.items():
            od = ods.get(sym)
            if od is None or not od.buy_orders or not od.sell_orders:
                continue
            m = math.log(K / S)
            info[sym] = (K, m)
            v = implied_total_vol(_mid(od), S, K)
            if v is not None:
                d1 = (-m + 0.5 * v * v) / v
                xs.append(m); ys.append(v); ws.append(max(S * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi), 1e-6))

        # 2) fit the smile, smooth its coefficients across ticks
        coef = fit_quadratic(xs, ys, ws) if len(xs) >= prm["min_points"] else None
        if coef is not None:
            prev = mem.get("smile")
            mem["smile"] = coef if prev is None else [_ema(prev[i], coef[i], prm["smile_span"]) for i in range(3)]
        coef = mem.get("smile")
        if coef is None:
            return result, 0, json.dumps(mem)

        # 3) price each voucher off the smile
        fair, delta = {}, {}
        for sym, (K, m) in info.items():
            v = max(coef[0] + coef[1] * m + coef[2] * m * m, 1e-4)
            fair[sym], delta[sym] = bs_call(S, K, v), bs_delta(S, K, v)

        # 4) take threshold, shrunk only if wobbles get clearly smaller than on the real days
        take = prm["take"]
        ts = prm.get("take_scale")
        if ts:
            dev = [abs(_mid(ods[sym]) - fair[sym]) for sym in fair if _mid(ods[sym]) >= 3]
            if dev:
                n = mem.get("wn", 0) + 1
                wob = mem.get("wob", 0.0)
                wob += (sum(dev) / len(dev) - wob) / min(n, ts["warmup"])
                mem["wob"], mem["wn"] = wob, n
                if n >= ts["warmup"] and wob < ts["gate"]:
                    take = max(ts["floor"], prm["take"] * wob / ts["ref"])

        # 5) quote each voucher; add up the book's delta
        net_delta = 0.0
        for sym in info:
            pos = state.position.get(sym, 0)
            net_delta += pos * delta[sym]
            result[sym] = market_make(sym, ods[sym], pos, fair[sym], take, prm["edge"], prm["skew"], LIMITS[sym])

        # 6) LYCHEE: market-make around its mid, drifting toward the delta-hedge position
        ly = prm["lychee"]
        target = max(-LIMITS[UNDERLYING], min(LIMITS[UNDERLYING], -ly["hedge"] * net_delta))
        result[UNDERLYING] = market_make(UNDERLYING, und, state.position.get(UNDERLYING, 0), S, ly["take"],
                                         ly["edge"], ly["skew"], ly["max_pos"], target=target)
        return result, 0, json.dumps(mem)
