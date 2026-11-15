import json
from math import ceil, erf, exp, floor, log, pi, sqrt

from datamodel import Order

# position limits (vouchers default to 50)
LIMITS = {
    "AMETHYST": 50, "TOFFEE_CAKE": 50, "PAPER_LANTERNS": 50, "TELLURIUM": 40,
    "JELLY": 50, "PEANUT_BUTTER": 50, "LYCHEE": 200,
    "DRAGONFRUIT": 40, "GRANADILLA": 40, "MANGOSTEEN": 40, "FRUIT_BASKET": 40,
    "WHITE_PEARLS": 20, "BLACK_PEARLS": 20, "GOLDEN_PEARLS": 20, "PINK_PEARLS": 20, "BLUE_PEARLS": 20,
}

PARAMS = {
    "AMETHYST": {"fair": 10000},
    "GOLDEN_PEARLS": {"jump": 3, "ramp": 3, "stall": 8},
    "PINK_PEARLS": {"jump": 3, "ramp": 999, "stall": 8, "edge": 2, "take": 3, "skew": 3, "vol_k": 1.5, "guard": 25},
    "TELLURIUM": {"jump": 25, "wait": 20, "hold": 250},
    "PAPER_LANTERNS": {"seg_len": 500, "noise": 1.06, "z": 3.0, "min_slope": 0.01, "min_move": 4,
                       "max_resid": 2.5, "span": 100, "trend_thr": 0.015},
    "TOFFEE_CAKE": {"mu0": 5000, "span": 3000, "enter": 15, "exit": 4},
    "VOUCHER": {"edge": 2, "take": 3, "skew": 0, "span": 50, "min_points": 5},
    "DEFAULT": {"span": 5, "soft": 0.05},
}

STRATEGY = {
    "AMETHYST": "fixed",
    "GOLDEN_PEARLS": "level",
    "PINK_PEARLS": "level",
    "TELLURIUM": "jump_drift",
    "PAPER_LANTERNS": "segments",
    "TOFFEE_CAKE": "mean_revert",
}

PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
MAX_QUOTE = 5
SQRT2 = sqrt(2)


def norm_cdf(x):
    return 0.5 * (1 + erf(x / SQRT2))


def call_price(S, K, vol):
    # Black-Scholes call, zero rates, vol = total vol (sigma * sqrt(T))
    if vol <= 1e-9:
        return max(S - K, 0.0)
    d1 = (log(S / K) + 0.5 * vol * vol) / vol
    return S * norm_cdf(d1) - K * norm_cdf(d1 - vol)


def implied_vol(price, S, K):
    # bisection, returns None if the price has no time value
    if price <= max(S - K, 0.0) + 0.25 or price >= S:
        return None
    lo, hi = 1e-4, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if call_price(S, K, mid) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def fit_smile(xs, ys, ws):
    # weighted least squares for y = a + b*x + c*x^2
    s = [0.0] * 5
    t = [0.0] * 3
    for x, y, w in zip(xs, ys, ws):
        q = 1.0
        for k in range(5):
            s[k] += w * q
            if k < 3:
                t[k] += w * q * y
            q *= x
    m = [[s[0], s[1], s[2], t[0]], [s[1], s[2], s[3], t[1]], [s[2], s[3], s[4], t[2]]]
    for i in range(3):
        piv = max(range(i, 3), key=lambda r: abs(m[r][i]))
        if abs(m[piv][i]) < 1e-12:
            return None
        m[i], m[piv] = m[piv], m[i]
        for r in range(3):
            if r != i:
                f = m[r][i] / m[i][i]
                for c in range(i, 4):
                    m[r][c] -= f * m[i][c]
    return [m[i][3] / m[i][i] for i in range(3)]


def ema(prev, x, span):
    return x if prev is None else prev + 2.0 / (span + 1.0) * (x - prev)


class Trader:
    def run(self, state):
        memory = json.loads(state.traderData) if state.traderData else {}
        shared = memory.setdefault("shared", {})
        self.timestamp = state.timestamp

        books = {p: d for p, d in state.order_depths.items() if d.buy_orders and d.sell_orders}
        voucher_fair = self.voucher_fair(books, shared)
        pink_fair = self.pink_fair(books, shared)

        result = {}
        for product, depth in books.items():
            limit = LIMITS.get(product, 50)
            position = state.position.get(product, 0)
            best_bid, best_ask = max(depth.buy_orders), min(depth.sell_orders)
            mid = (best_bid + best_ask) / 2
            mem = memory.setdefault(product, {})
            try:
                if "VOUCHER" in product:
                    fair = voucher_fair.get(product)
                    result[product] = [] if fair is None else self.make_market(
                        product, depth, position, limit, fair, PARAMS["VOUCHER"])
                    continue
                params = PARAMS.get(product, PARAMS["DEFAULT"])
                strategy = getattr(self, STRATEGY.get(product, "market_make"))
                result[product] = strategy(product, depth, position, limit, best_bid, best_ask, mid, mem, params)
                # level tracker still runs for PINK so it's ready if the pearl-sum rule switches off
                if product == "PINK_PEARLS" and pink_fair is not None:
                    extra = params["vol_k"] * shared.get("pink_vol", 0.0)
                    result[product] = self.make_market(product, depth, position, limit, pink_fair, params, extra)
            except Exception:
                result[product] = []

        for key, value in shared.items():
            if isinstance(value, float):
                shared[key] = round(value, 4)
        return result, 0, json.dumps(memory, separators=(",", ":"))

    # ----- order helpers (all stay within position limits) -----

    @staticmethod
    def take(product, depth, fair, edge, position, limit, orders):
        bought = sold = 0
        for price in sorted(depth.sell_orders):
            if price > fair - edge or position + bought >= limit:
                break
            qty = min(-depth.sell_orders[price], limit - position - bought)
            orders.append(Order(product, price, qty))
            bought += qty
        for price in sorted(depth.buy_orders, reverse=True):
            if price < fair + edge or position - sold <= -limit:
                break
            qty = min(depth.buy_orders[price], limit + position - sold)
            orders.append(Order(product, price, -qty))
            sold += qty
        return bought, sold

    @staticmethod
    def quote(product, fair, position, limit, best_bid, best_ask, bought, sold, orders, soft=1.0, size=MAX_QUOTE):
        # join the best bid/ask (no queue priority here, so joining fills as often as improving)
        if best_bid < fair and position < soft * limit and limit - position - bought > 0:
            orders.append(Order(product, best_bid, min(size, limit - position - bought)))
        if best_ask > fair and position > -soft * limit and limit + position - sold > 0:
            orders.append(Order(product, best_ask, -min(size, limit + position - sold)))

    @staticmethod
    def to_target(product, depth, target, position, limit, orders):
        # cross the spread level by level until the position reaches target
        need = max(-limit, min(limit, target)) - position
        if need > 0:
            for price in sorted(depth.sell_orders):
                if need == 0:
                    break
                qty = min(-depth.sell_orders[price], need)
                orders.append(Order(product, price, qty))
                need -= qty
        elif need < 0:
            for price in sorted(depth.buy_orders, reverse=True):
                if need == 0:
                    break
                qty = min(depth.buy_orders[price], -need)
                orders.append(Order(product, price, -qty))
                need += qty

    @staticmethod
    def make_market(product, depth, position, limit, fair, params, extra_edge=0.0):
        # take anything at least `take` through fair, then quote leftover size at the touch,
        # no closer than `edge` to fair, with the price skewed against inventory
        orders = []
        buy_cap, sell_cap = limit - position, limit + position
        pos_after = position
        asks = sorted(depth.sell_orders.items())
        bids = sorted(depth.buy_orders.items(), reverse=True)
        taken_asks, taken_bids = set(), set()
        for price, vol in asks:
            if buy_cap <= 0 or price > fair - params["take"]:
                break
            qty = min(-vol, buy_cap)
            orders.append(Order(product, price, qty))
            buy_cap -= qty
            pos_after += qty
            taken_asks.add(price)
        for price, vol in bids:
            if sell_cap <= 0 or price < fair + params["take"]:
                break
            qty = min(vol, sell_cap)
            orders.append(Order(product, price, -qty))
            sell_cap -= qty
            pos_after -= qty
            taken_bids.add(price)

        reservation = fair - params["skew"] * pos_after / limit
        edge = params["edge"] + extra_edge
        rest_bids = [p for p, _ in bids if p not in taken_bids]
        rest_asks = [p for p, _ in asks if p not in taken_asks]
        bid = min(rest_bids[0] if rest_bids else floor(fair) - 1, floor(reservation - edge))
        ask = max(rest_asks[0] if rest_asks else ceil(fair) + 1, ceil(reservation + edge))
        if asks:
            bid = min(bid, asks[0][0] - 1)
        if bids:
            ask = max(ask, bids[0][0] + 1)
        if bid >= ask:
            bid, ask = ask - 1, bid + 1
        if buy_cap > 0:
            orders.append(Order(product, int(bid), int(buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, int(ask), -int(sell_cap)))
        return orders

    # ----- strategies -----

    def fixed(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # AMETHYST: fair value is always 10000
        orders = []
        bought, sold = self.take(product, depth, params["fair"], 1, position, limit, orders)
        self.quote(product, params["fair"], position, limit, best_bid, best_ask, bought, sold, orders)
        return orders

    def level(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # flat price level: small moves (ramp..5*jump) are ridden as slides, bigger ones re-anchor
        orders = []
        lvl = mem.get("lv", mid)
        n = mem.get("n", 0)
        mode = mem.get("mode", 0)
        if mode == 0:
            dev = mid - lvl
            if params["ramp"] < abs(dev) <= 5 * params["jump"]:
                mode = 1 if dev > 0 else -1
                mem["ext"] = mid
                mem["k"] = 0
            elif abs(dev) > params["jump"]:
                lvl, n = mid, 1
            else:
                n = min(n + 1, 200)
                lvl += (mid - lvl) / n
        if mode:
            if (mode < 0 and mid < mem["ext"]) or (mode > 0 and mid > mem["ext"]):
                mem["ext"] = mid
                mem["k"] = 0
            else:
                mem["k"] += 1
            if mem["k"] >= params["stall"]:  # slide has stopped
                mode, lvl, n = 0, mid, 1
            else:
                self.to_target(product, depth, mode * limit, position, limit, orders)
                mem.update(lv=lvl, n=n, mode=mode)
                return orders
        bought, sold = self.take(product, depth, lvl, 1, position, limit, orders)
        self.quote(product, lvl, position, limit, best_bid, best_ask, bought, sold, orders)
        mem.update(lv=lvl, n=n, mode=mode)
        return orders

    def jump_drift(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # TELLURIUM: after a jump, trade the direction of the move from tick 3 to tick `wait`, until `hold`
        orders = []
        hist = (mem.get("h", []) + [mid])[-4:]
        mem["h"] = hist
        k = mem.get("k", -1)  # ticks since the jump, -1 when idle
        if len(hist) == 4 and abs(hist[-1] - hist[0]) > params["jump"] and (k < 0 or k > 5):
            k = 0
            mem["ref"] = None
        elif k >= 0:
            k += 1
        if k == 3:
            mem["ref"] = mid
        target = 0
        if params["wait"] <= k <= params["hold"] and mem.get("ref") is not None:
            if k == params["wait"]:
                mem["dir"] = 1 if mid > mem["ref"] else -1 if mid < mem["ref"] else 0
            target = mem.get("dir", 0) * limit
        elif k > params["hold"]:
            k = -1
        mem["k"] = k
        self.to_target(product, depth, target, position, limit, orders)
        return orders

    def segments(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # PAPER_LANTERNS: fair value is a continuous line whose slope changes every seg_len ticks.
        # Estimate each new slope starting from where the last segment ended, hold +-limit once it's clear.
        orders = []
        seg_len = params["seg_len"]
        seg, x = divmod(self.timestamp // 100, seg_len)

        # EMA trend, kept updated in case we need to fall back to it
        alpha = 2 / (params["span"] + 1)
        smooth = mem.get("f", mid)
        new_smooth = smooth + alpha * (mid - smooth)
        trend = mem.get("sl", 0.0) + alpha * ((new_smooth - smooth) - mem.get("sl", 0.0))
        mem.update(f=new_smooth, sl=trend)

        if mem.get("seg") != seg:
            # close out the previous segment: its fitted end point anchors the next line
            n, sx, sy, sxy, sxx, syy = mem.get("s", [0] * 6)
            den = n * sxx - sx * sx
            if n > 50 and den > 0:
                b = (n * sxy - sx * sy) / den
                c0 = (sy - b * sx) / n
                mem["anchor"] = mem.get("y0", 0) + c0 + b * seg_len
                resid_var = (syy - c0 * sy - b * sxy) / n
                mem["bad"] = (mem.get("bad", []) + [resid_var > params["max_resid"]])[-3:]
                if sum(mem["bad"]) >= 2:  # segments aren't straight anymore, stop trusting the grid
                    mem["fallback"] = 1
            else:
                mem["anchor"] = None
            mem.update(seg=seg, s=[0] * 6, c=[0.0, 0.0], y0=mid)

        y = mid - mem["y0"]
        s = mem["s"]
        s[0] += 1
        s[1] += x
        s[2] += y
        s[3] += x * y
        s[4] += x * x
        s[5] += y * y

        if mem.get("fallback"):
            thr = params["trend_thr"]
            target = limit if trend > thr else -limit if trend < -thr else position
            self.to_target(product, depth, target, position, limit, orders)
            return orders

        if mem["anchor"] is not None:
            c = mem["c"]
            c[0] += x * (mid - mem["anchor"])
            c[1] += x * x
            if c[1]:
                slope, se = c[0] / c[1], params["noise"] / sqrt(c[1])
            else:
                slope, se = 0.0, 1e9
        else:  # first segment of the day has no anchor
            n, sx, sy, sxy, sxx, _ = s
            den = n * sxx - sx * sx
            if n > 2 and den > 0:
                slope, se = (n * sxy - sx * sy) / den, params["noise"] * sqrt(n / den)
            else:
                slope, se = 0.0, 1e9

        target = position
        if abs(slope) > max(params["min_slope"], params["z"] * se) and abs(slope) * (seg_len - x) > params["min_move"]:
            target = limit if slope > 0 else -limit
        self.to_target(product, depth, target, position, limit, orders)
        return orders

    def mean_revert(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # TOFFEE_CAKE: snaps back to a slow mean. Only hit quotes at least `enter` away from it,
        # exit once price has gone `exit` past the mean
        orders = []
        mu = mem.get("mu", params["mu0"])
        mu += (mid - mu) / params["span"]
        mem["mu"] = mu
        if best_ask <= mu - params["enter"] or best_bid >= mu + params["enter"]:
            self.take(product, depth, mu, params["enter"], position, limit, orders)
        elif (position > 0 and best_bid >= mu + params["exit"]) or (position < 0 and best_ask <= mu - params["exit"]):
            self.to_target(product, depth, 0, position, limit, orders)
        return orders

    def market_make(self, product, depth, position, limit, best_bid, best_ask, mid, mem, params):
        # everything else: quote around a short EMA and keep inventory tiny
        orders = []
        alpha = 2 / (params["span"] + 1)
        fair = mem.get("f", mid)
        fair += alpha * (mid - fair)
        mem["f"] = fair
        self.quote(product, fair, position, limit, best_bid, best_ask, 0, 0, orders, soft=params["soft"])
        return orders

    # ----- fair values that use other products -----

    def voucher_fair(self, books, shared):
        # fit a vega-weighted smile (implied total vol vs log-moneyness) across strikes, smooth it,
        # then price every voucher off it
        if "LYCHEE" not in books:
            return {}
        lychee = books["LYCHEE"]
        S = (max(lychee.buy_orders) + min(lychee.sell_orders)) / 2
        xs, ys, ws, moneyness = [], [], [], {}
        for K in STRIKES:
            depth = books.get(f"VOUCHER_{K}")
            if depth is None:
                continue
            x = log(K / S)
            moneyness[K] = x
            vol = implied_vol((max(depth.buy_orders) + min(depth.sell_orders)) / 2, S, K)
            if vol is not None:
                d1 = (-x + 0.5 * vol * vol) / vol
                xs.append(x)
                ys.append(vol)
                ws.append(max(S * exp(-0.5 * d1 * d1) / sqrt(2 * pi), 1e-6))

        span = PARAMS["VOUCHER"]["span"]
        coef = fit_smile(xs, ys, ws) if len(xs) >= PARAMS["VOUCHER"]["min_points"] else None
        if coef is not None:
            old = shared.get("smile")
            shared["smile"] = coef if old is None else [ema(o, c, span) for o, c in zip(old, coef)]
        coef = shared.get("smile")
        if coef is None:
            return {}
        return {f"VOUCHER_{K}": call_price(S, K, max(coef[0] + coef[1] * x + coef[2] * x * x, 1e-4))
                for K, x in moneyness.items()}

    def pink_fair(self, books, shared):
        # the five pearls always sum to ~50,000 and PINK jumps to close any gap,
        # so PINK's fair value is its mid minus the gap. Turned off for the day if the gap gets too big.
        if any(p not in books for p in PEARLS):
            return None
        mids = {p: (max(books[p].buy_orders) + min(books[p].sell_orders)) / 2 for p in PEARLS}
        pink = mids["PINK_PEARLS"]
        last = shared.get("pink_last")
        if last is not None:
            shared["pink_vol"] = ema(shared.get("pink_vol"), abs(pink - last), 50)
        shared["pink_last"] = pink
        gap = sum(mids.values()) - 50000
        if abs(gap) > PARAMS["PINK_PEARLS"]["guard"]:
            shared["pink_off"] = 1
        return None if shared.get("pink_off") else pink - gap
