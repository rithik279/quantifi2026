"""
QuantiFi 2026 trader: one Trader class, four strategy families.

  1. Single products  (AMETHYST, JELLY, PEANUT_BUTTER; TOFFEE_CAKE, PAPER_LANTERNS and TELLURIUM
     use the directional strategies in _T1 further down)
     Inventory-skewed market maker (RCFA lineage): estimate fair value, take any quote that is
     clearly mispriced, then quote inside the spread with prices shifted against our inventory,
     and widen when the market gets jumpy.
  2. Basket family    (FRUIT_BASKET = 2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN)
     Same market maker on all four. Premium trading was tested three ways and rejected.
  3. Options          (LYCHEE + 10 VOUCHER strikes)
     Every tick: back out each voucher's implied volatility, fit a smile across strikes,
     price each voucher off the smile, make markets around that price, and hedge the
     book's net delta by skewing LYCHEE quotes toward the hedge position.
  4. Pearls           (five pearls whose prices sum to ~50,000)
     PINK is priced off the sum rule (fair = own mid - deviation of the five-pearl sum from
     50,000), with a guardrail that drops the signal if the rule breaks. The others are plain
     market making. GOLDEN is handled by the plateau strategy in _T1.

Only the standard library is used (no numpy) so the file runs on any backtesting engine.
All state that must survive between ticks lives in traderData (the engine may not keep
Python objects alive between ticks).
"""
import json
import math
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

LIMITS = {
    "AMETHYST": 50, "TOFFEE_CAKE": 50, "PAPER_LANTERNS": 50, "TELLURIUM": 40,
    "JELLY": 50, "PEANUT_BUTTER": 50,
    "DRAGONFRUIT": 40, "GRANADILLA": 40, "MANGOSTEEN": 40, "FRUIT_BASKET": 40,
    "LYCHEE": 200,
    "WHITE_PEARLS": 20, "BLACK_PEARLS": 20, "GOLDEN_PEARLS": 20, "PINK_PEARLS": 20, "BLUE_PEARLS": 20,
}
STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = {f"VOUCHER_{k}": k for k in STRIKES}
for _v in VOUCHERS:
    LIMITS[_v] = 50

BASKET = "FRUIT_BASKET"
BASKET_WEIGHTS = {"DRAGONFRUIT": 2, "GRANADILLA": 3, "MANGOSTEEN": 1}
PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
PEARL_SUM = 50_000

# ---------------------------------------------------------------------------------------
# Parameters. Every number here was chosen by leave-one-day-out cross-validation
# (tune on two days, score on the third). See the README / abstract for the grid.
#   fair     : how fair value is estimated
#   edge     : minimum distance (coins) between our quote and our reservation price
#   take     : take a bot quote if it is at least this far through fair value
#   skew     : how far (coins) we shift both quotes when at the full position limit
#   vol_k    : extra edge per unit of recent absolute price change ("Mode C" widening)
#   max_pos  : soft position cap below the exchange limit (used where inventory risk > spread income)
# ---------------------------------------------------------------------------------------
DEFAULT_PARAMS: Dict[str, dict] = {
    "AMETHYST": {"fair": "fixed", "value": 10000, "edge": 1, "take": 2, "skew": 0, "vol_k": 0.0},
    "JELLY": {"fair": "mid", "edge": 2, "take": 99, "skew": 10, "vol_k": 0.0, "span": 5, "max_pos": 5},
    "PEANUT_BUTTER": {"fair": "mid", "edge": 2, "take": 99, "skew": 10, "vol_k": 0.0, "max_pos": 5},
    "DRAGONFRUIT": {"fair": "ema", "edge": 2, "take": 5, "skew": 0, "vol_k": 1.5, "span": 5},
    "GRANADILLA": {"fair": "mid", "edge": 2, "take": 99, "skew": 10, "vol_k": 0.0, "span": 5, "max_pos": 5},
    "MANGOSTEEN": {"fair": "mid", "edge": 2, "take": 3, "skew": 0, "vol_k": 0.0},
    "FRUIT_BASKET": {"fair": "mid", "edge": 2, "take": 99, "skew": 10, "vol_k": 0.0, "max_pos": 5},
    "LYCHEE": {"fair": "mid", "edge": 1, "take": 2, "skew": 3.0, "vol_k": 0.0, "hedge": 1.0, "max_pos": 40},
    "OPTIONS": {"edge": 2, "take": 3, "skew": 0, "smile_span": 50, "shade": 0.0, "min_points": 5},
    "WHITE_PEARLS": {"fair": "ema", "edge": 4, "take": 5, "skew": 0, "vol_k": 0.0, "span": 5},
    "BLACK_PEARLS": {"fair": "ema", "edge": 2, "take": 3, "skew": 3, "vol_k": 0.0, "span": 5},
    "BLUE_PEARLS": {"fair": "ema", "edge": 4, "take": 5, "skew": 3, "vol_k": 0.0, "span": 5},
    "PINK_PEARLS": {"fair": "mid", "edge": 2, "take": 3, "skew": 3, "vol_k": 1.5, "alpha": 1.0, "guard": 40.0},
}

SINGLES = ["AMETHYST", "JELLY", "PEANUT_BUTTER"]   # TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM: see _T1


# =========================================================================================
# Small math helpers (no numpy)
# =========================================================================================
def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, v: float) -> float:
    """Black-Scholes call with zero rates, using TOTAL volatility v = sigma * sqrt(T).
    Working in total vol means we never need to know the calendar time to expiry."""
    if v <= 1e-9:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * v * v) / v
    return S * norm_cdf(d1) - K * norm_cdf(d1 - v)


def bs_delta(S: float, K: float, v: float) -> float:
    if v <= 1e-9:
        return 1.0 if S > K else 0.0
    return norm_cdf((math.log(S / K) + 0.5 * v * v) / v)


def implied_total_vol(price: float, S: float, K: float):
    """Bisection on total vol. Returns None when the price carries no time value."""
    intrinsic = max(S - K, 0.0)
    if price <= intrinsic + 0.25 or price >= S:
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
    """Weighted least squares for y = a + b x + c x^2 (3x3 normal equations)."""
    s = [0.0] * 5
    t = [0.0] * 3
    for x, y, w in zip(xs, ys, ws):
        p = 1.0
        for k in range(5):
            s[k] += w * p
            if k < 3:
                t[k] += w * p * y
            p *= x
    A = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
    # Gaussian elimination
    M = [A[i] + [t[i]] for i in range(3)]
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


def ema(prev, x, span):
    if prev is None:
        return x
    a = 2.0 / (span + 1.0)
    return prev + a * (x - prev)


# =========================================================================================
# Order book helpers
# =========================================================================================
def best_bid(od: OrderDepth):
    return max(od.buy_orders) if od.buy_orders else None


def best_ask(od: OrderDepth):
    return min(od.sell_orders) if od.sell_orders else None


def mid_price(od: OrderDepth):
    b, a = best_bid(od), best_ask(od)
    if b is None or a is None:
        return None
    return 0.5 * (b + a)


def wall_mid(od: OrderDepth):
    """Midpoint of the largest-volume bid and ask levels. Kept as an option: in this dataset the
    level volumes are random, and the plain mid predicts future prices better (tested)."""
    if not od.buy_orders or not od.sell_orders:
        return None
    wb = max(od.buy_orders.items(), key=lambda kv: kv[1])[0]
    wa = min(od.sell_orders.items(), key=lambda kv: kv[1])[0]   # sells are negative volumes
    return 0.5 * (wb + wa)




# =========================================================================================
# Directional strategies merged in from trader_1.py. Each beat our market maker on these
# products in every one of 27 neighbouring parameter settings (robust, not a lucky tune):
#   TELLURIUM      : after a jump (3-tick move > 5.5x local vol), trade the drift that follows
#                    (wait 20 ticks to confirm direction, hold to tick 250)
#   PAPER_LANTERNS : follow the slope of a smoothed price (threshold scaled by typical tick move)
#   TOFFEE_CAKE    : buy far below / sell far above a slow moving anchor (~5,000), exit near it
#   GOLDEN_PEARLS  : quote around the current plateau; ride the slides between plateaus
# =========================================================================================
from math import erf as _erf
T1_LIM = {'TELLURIUM': 40, 'PAPER_LANTERNS': 50, 'TOFFEE_CAKE': 50, 'GOLDEN_PEARLS': 20}
P = {
    'GOLDEN_PEARLS': {'jump': 3, 'ramp': 3, 'stall': 8},
    'TELLURIUM': {'jump': 25, 'jk': 5.5, 'w': 20, 'H': 250},
    'PAPER_LANTERNS': {'span': 100, 'thr': 0.015, 'tk': 0.012},
    'TOFFEE_CAKE': {'mu0': 5000, 'band': 100, 'span': 3000, 'enter': 15, 'exit': 4},
}
QMAX = 5
T1_STRAT = {'GOLDEN_PEARLS': 'level', 'TELLURIUM': 'jumpdrift', 'PAPER_LANTERNS': 'trend', 'TOFFEE_CAKE': 'meanrev'}

class _T1:
    """Directional strategies (from trader_1.py)."""
    # ---------- order helpers (always within position limits) ----------
    @staticmethod
    def take(p, d, fv, edge, pos, L, o):
        buy = sell = 0
        for px in sorted(d.sell_orders):
            if px > fv - edge or pos + buy >= L: break
            q = min(-d.sell_orders[px], L - pos - buy); o.append(Order(p, px, q)); buy += q
        for px in sorted(d.buy_orders, reverse=True):
            if px < fv + edge or pos - sell <= -L: break
            q = min(d.buy_orders[px], L + pos - sell); o.append(Order(p, px, -q)); sell += q
        return buy, sell

    @staticmethod
    def quote(p, fv, pos, L, bb, ba, buy, sell, o, soft=1.0, size=QMAX):
        """Join the touch (here joining fills as often as improving, at a better price). size caps each resting order."""
        if bb < fv and pos < soft * L and L - pos - buy > 0: o.append(Order(p, bb, min(size, L - pos - buy)))
        if ba > fv and pos > -soft * L and L + pos - sell > 0: o.append(Order(p, ba, -min(size, L + pos - sell)))

    @staticmethod
    def to_target(p, d, tgt, pos, L, o):
        tgt = max(-L, min(L, tgt)); need = tgt - pos
        book = sorted(d.sell_orders) if need > 0 else sorted(d.buy_orders, reverse=True)
        for px in book:
            if need == 0: break
            q = min(abs(d.sell_orders[px] if need > 0 else d.buy_orders[px]), abs(need))
            o.append(Order(p, px, q if need > 0 else -q)); need -= q if need > 0 else -q

    # ---------- strategies ----------
    def fixed(self, p, d, pos, L, bb, ba, mid, m, prm):
        o = []; b, s = self.take(p, d, prm['fv'], 1, pos, L, o)
        self.quote(p, prm['fv'], pos, L, bb, ba, b, s, o); return o

    def level(self, p, d, pos, L, bb, ba, mid, m, prm):
        o = []; lv = m.get('lv', mid); n = m.get('n', 0); mode = m.get('mode', 0)
        if mode == 0:
            dev = mid - lv
            if prm['ramp'] < abs(dev) <= 5 * prm['jump']:
                mode = 1 if dev > 0 else -1; m['ext'] = mid; m['k'] = 0
            elif abs(dev) > prm['jump']:
                lv, n = mid, 1
            else:
                n = min(n + 1, 200); lv += (mid - lv) / n
        if mode:
            if (mode < 0 and mid < m['ext']) or (mode > 0 and mid > m['ext']): m['ext'] = mid; m['k'] = 0
            else: m['k'] += 1
            if m['k'] >= prm['stall']: mode, lv, n = 0, mid, 1
            else:
                self.to_target(p, d, mode * L, pos, L, o); m.update(lv=lv, n=n, mode=mode); return o
        b, s = self.take(p, d, lv, 1, pos, L, o); self.quote(p, lv, pos, L, bb, ba, b, s, o)
        m.update(lv=lv, n=n, mode=mode); return o

    def jumpdrift(self, p, d, pos, L, bb, ba, mid, m, prm):
        o = []; h = (m.get('h', []) + [mid])[-4:]; m['h'] = h; k = m.get('k', -1)
        # Jump = 3-tick move larger than jk x local volatility. Local vol uses bipower variation
        # (product of consecutive absolute moves), which a single jump barely inflates
        # (Barndorff-Nielsen & Shephard 2006; Lee & Mykland 2008). Falls back to a fixed
        # threshold until the estimate exists.
        thr = prm['jump']
        if len(h) >= 3:
            bp = abs(h[-1] - h[-2]) * abs(h[-2] - h[-3])
            m['bv'] = bp if m.get('bv') is None else m['bv'] + (bp - m['bv']) / 500.0
            if m['bv'] > 0:
                thr = prm['jk'] * (m['bv'] * 1.5707963 * 3) ** 0.5
        if len(h) == 4 and abs(h[-1] - h[0]) > thr and (k < 0 or k > 5): k = 0; m['ref'] = None
        elif k >= 0: k += 1
        if k == 3: m['ref'] = mid
        tgt = 0
        if prm['w'] <= k <= prm['H'] and m.get('ref') is not None:
            if k == prm['w']: m['dir'] = 1 if mid > m['ref'] else -1 if mid < m['ref'] else 0
            tgt = m.get('dir', 0) * L
        elif k > prm['H']: k = -1
        m['k'] = k; self.to_target(p, d, tgt, pos, L, o); return o

    def trend(self, p, d, pos, L, bb, ba, mid, m, prm):
        o = []; a = 2 / (prm['span'] + 1); f = m.get('f', mid); fn = f + a * (mid - f)
        sl = m.get('sl', 0.0) + a * ((fn - f) - m.get('sl', 0.0)); m.update(f=fn, sl=sl)
        # Trend threshold scaled by the product's typical tick move (volatility-scaled signal, as in
        # time-series momentum: Moskowitz, Ooi & Pedersen 2012). Same as the old fixed 0.015 at this
        # data's volatility, but keeps the false-signal rate constant if volatility changes.
        pm = m.get('pm', mid); m['pm'] = mid
        m['av'] = abs(mid - pm) if m.get('av') is None else m['av'] + (abs(mid - pm) - m['av']) / 2000.0
        thr = prm['tk'] * m['av'] if m['av'] > 0 else prm['thr']
        tgt = L if sl > thr else -L if sl < -thr else pos
        self.to_target(p, d, tgt, pos, L, o); return o

    def meanrev(self, p, d, pos, L, bb, ba, mid, m, prm):
        if 'mu' not in m:
            m['mu'] = prm['mu0'] if abs(mid - prm['mu0']) <= prm['band'] else mid
        o = []; mu = m['mu']; mu += (mid - mu) / prm['span']; m['mu'] = mu
        if ba <= mu - prm['enter']: tgt = L
        elif bb >= mu + prm['enter']: tgt = -L
        elif (pos > 0 and bb >= mu + prm['exit']) or (pos < 0 and ba <= mu - prm['exit']): tgt = 0
        else: tgt = pos
        self.to_target(p, d, tgt, pos, L, o); return o



# =========================================================================================
# Trader
# =========================================================================================
class Trader:
    def __init__(self, params: Dict[str, dict] = None):
        self.params = DEFAULT_PARAMS if params is None else params

    # ---------------------------------------------------------------- core market maker
    def market_make(self, product: str, od: OrderDepth, position: int, fair: float,
                    prm: dict, mem: dict, target: float = 0.0, extra_edge: float = 0.0,
                    quote: bool = True) -> List[Order]:
        """
        RCFA-style inventory-skewed market maker.
          fair       : our estimate of what the product is worth right now
          target     : the position we would like to drift toward (0 normally; the delta
                       hedge for LYCHEE)
          extra_edge : added width (volatility regime, pauses)
        Steps: (1) take mispriced bot quotes, (2) quote inside the spread around a
        reservation price shifted against our inventory, (3) never let total orders on
        either side exceed what the position limit allows.
        """
        limit = LIMITS[product]
        # soft cap: for random-walk products with few fills we deliberately hold far less than
        # the exchange limit, because inventory risk there dwarfs the spread we earn
        cap = min(limit, prm.get("max_pos", limit))
        orders: List[Order] = []
        buy_cap = max(0, min(limit - position, cap - position))
        sell_cap = max(0, min(limit + position, cap + position))
        take = prm["take"]

        # Mode C: widen when recent moves are large (stored per product)
        if prm.get("vol_k", 0.0) > 0:
            extra_edge += prm["vol_k"] * mem.get("vol_" + product, 0.0)

        # 1) TAKE: hit quotes that are clearly through fair value
        asks = sorted(od.sell_orders.items())
        bids = sorted(od.buy_orders.items(), reverse=True)
        taken_ask, taken_bid = set(), set()
        pos_after = position
        for px, vol in asks:
            if buy_cap <= 0 or px > fair - take:
                break
            q = min(-vol, buy_cap)
            orders.append(Order(product, px, q))
            buy_cap -= q
            pos_after += q
            taken_ask.add(px)
        for px, vol in bids:
            if sell_cap <= 0 or px < fair + take:
                break
            q = min(vol, sell_cap)
            orders.append(Order(product, px, -q))
            sell_cap -= q
            pos_after -= q
            taken_bid.add(px)

        if not quote:
            return orders

        # 2) MAKE: reservation price shifted against inventory (relative to target)
        reservation = fair - prm["skew"] * (pos_after - target) / cap
        edge = prm["edge"] + extra_edge

        rem_bids = [px for px, _ in bids if px not in taken_bid]
        rem_asks = [px for px, _ in asks if px not in taken_ask]
        bb = rem_bids[0] if rem_bids else math.floor(fair) - 1
        ba = rem_asks[0] if rem_asks else math.ceil(fair) + 1

        # Quote AT the best bid/ask, not one tick inside. Every market trade in this simulator prints
        # exactly at the touch, and a resting order fills when a trade prints at or through its price,
        # so improving by a tick wins no extra fills and just gives away a coin per fill
        # (the price/fill-probability trade-off of Hollifield, Miller & Sandas 2004 collapses here).
        imp = 1 if prm.get("penny") else 0
        bid_px = min(bb + imp, math.floor(reservation - edge))
        ask_px = max(ba - imp, math.ceil(reservation + edge))
        # Never let a resting quote cross the book (crossing is what the TAKE step is for)
        if asks:
            bid_px = min(bid_px, asks[0][0] - 1)
        if bids:
            ask_px = max(ask_px, bids[0][0] + 1)
        if bid_px >= ask_px:
            bid_px, ask_px = ask_px - 1, bid_px + 1

        if buy_cap > 0:
            orders.append(Order(product, int(bid_px), int(buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, int(ask_px), -int(sell_cap)))
        return orders

    # ---------------------------------------------------------------- fair value per product
    def basic_fair(self, product: str, od: OrderDepth, prm: dict, mem: dict):
        kind = prm["fair"]
        if kind == "fixed":
            return float(prm["value"])
        wm = mid_price(od)
        if kind == "mid":
            return wm
        if kind == "wall":
            w = wall_mid(od)
            return wm if w is None else w
        if kind == "ema":
            key = "ema_" + product
            mem[key] = ema(mem.get(key), wm, prm["span"])
            return mem[key]
        return wm

    def update_vol(self, product: str, ref: float, mem: dict, span: int = 50):
        last = mem.get("last_" + product)
        if last is not None:
            mem["vol_" + product] = ema(mem.get("vol_" + product), abs(ref - last), span)
        mem["last_" + product] = ref

    # ---------------------------------------------------------------- 1) singles
    def trade_singles(self, state: TradingState, mem: dict, result: dict):
        for p in SINGLES:
            od = state.order_depths.get(p)
            if od is None or not od.buy_orders or not od.sell_orders:
                continue
            prm = self.params[p]
            pos = state.position.get(p, 0)
            fair = self.basic_fair(p, od, prm, mem)
            m = mid_price(od)
            self.update_vol(p, m, mem)


            result[p] = self.market_make(p, od, pos, fair, prm, mem)

    # ---------------------------------------------------------------- 2) basket family
    def trade_basket(self, state: TradingState, mem: dict, result: dict):
        ods = state.order_depths
        names = [BASKET] + list(BASKET_WEIGHTS)
        if any(n not in ods or not ods[n].buy_orders or not ods[n].sell_orders for n in names):
            return
        fairs = {n: self.basic_fair(n, ods[n], self.params[n], mem) for n in names}

        # The basket premium (basket - 2 DRAGONFRUIT - 3 GRANADILLA - 1 MANGOSTEEN) is not anchored in
        # this data: trading it as mean reversion, momentum, or Prosperity-style +/- thresholds all
        # lost money out of sample (day -2 trended ~1,700). So each leg is simply market-made.

        for n in names:
            od = ods[n]
            self.update_vol(n, mid_price(od), mem)
            result[n] = self.market_make(n, od, state.position.get(n, 0), fairs[n], self.params[n], mem)

    # ---------------------------------------------------------------- 3) options
    def trade_options(self, state: TradingState, mem: dict, result: dict):
        ods = state.order_depths
        und = "LYCHEE"
        if und not in ods or not ods[und].buy_orders or not ods[und].sell_orders:
            return
        op = self.params["OPTIONS"]
        S = mid_price(ods[und])

        # (a) implied total vol for every voucher with a usable price
        xs, ys, ws, info = [], [], [], {}
        for sym, K in VOUCHERS.items():
            od = ods.get(sym)
            if od is None or not od.buy_orders or not od.sell_orders:
                continue
            px = mid_price(od)
            v = implied_total_vol(px, S, K)
            m = math.log(K / S)
            info[sym] = (K, m)
            if v is not None:
                # weight ~ vega so near-the-money strikes (most informative) count more
                d1 = (-m + 0.5 * v * v) / v
                vega = S * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
                xs.append(m); ys.append(v); ws.append(max(vega, 1e-6))

        # (b) fit the smile, smooth the coefficients across ticks to strip quote noise
        coef = None
        if len(xs) >= op["min_points"]:
            coef = fit_quadratic(xs, ys, ws)
        prev = mem.get("smile")
        if coef is not None:
            if prev is None:
                mem["smile"] = coef
            else:
                mem["smile"] = [ema(prev[i], coef[i], op["smile_span"]) for i in range(3)]
        coef = mem.get("smile")
        if coef is None:
            return

        # (c) price + quote each voucher; accumulate book delta
        net_delta = 0.0
        for sym, (K, m) in info.items():
            v = max(coef[0] + coef[1] * m + coef[2] * m * m, 1e-4)
            fair = bs_call(S, K, v)
            # shade < 0 leans short volatility (options looked rich vs realised vol in-sample)
            if op["shade"] != 0.0:
                d1 = (-m + 0.5 * v * v) / v
                vega = S * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
                fair += op["shade"] * vega * 0.001
            pos = state.position.get(sym, 0)
            net_delta += pos * bs_delta(S, K, v)
            result[sym] = self.market_make(sym, ods[sym], pos, fair, op, mem)

        # (d) LYCHEE: market make, but drift toward the delta-hedging position
        up = self.params[und]
        target = max(-LIMITS[und], min(LIMITS[und], -up["hedge"] * net_delta))
        self.update_vol(und, mid_price(ods[und]), mem)
        result[und] = self.market_make(und, ods[und], state.position.get(und, 0), S, up, mem,
                                       target=target)

    # ---------------------------------------------------------------- 4) pearls
    def trade_pearls(self, state: TradingState, mem: dict, result: dict):
        ods = state.order_depths
        if any(p not in ods or not ods[p].buy_orders or not ods[p].sell_orders for p in PEARLS):
            return
        mids = {p: mid_price(ods[p]) for p in PEARLS}
        sum_dev = sum(mids.values()) - PEARL_SUM
        mem["sum_dev_ema"] = ema(mem.get("sum_dev_ema"), sum_dev, 200)

        for p in PEARLS:
            if p == "GOLDEN_PEARLS":      # traded by the _T1 plateau strategy
                continue
            prm = self.params[p]
            od = ods[p]
            pos = state.position.get(p, 0)
            fair = self.basic_fair(p, od, prm, mem)
            self.update_vol(p, mids[p], mem)
            extra = 0.0
            quote = True

            if p == "PINK_PEARLS":
                # PINK is the pearl that closes gaps in the 50,000 sum rule. Guardrail: if the
                # sum drifts far from 50,000 for a sustained period, the rule has broken and we
                # fall back to plain market making.
                if abs(mem["sum_dev_ema"]) < prm["guard"]:
                    fair = mids[p] - prm["alpha"] * sum_dev


            result[p] = self.market_make(p, od, pos, fair, prm, mem, extra_edge=extra, quote=quote)

    # ---------------------------------------------------------------- entry point
    def run(self, state: TradingState):
        try:
            mem = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            mem = {}
        result: Dict[str, List[Order]] = {}

        # Each family is isolated: an error in one never stops the others from trading.
        for fn in (self.trade_singles, self.trade_basket, self.trade_options, self.trade_pearls):
            try:
                fn(state, mem, result)
            except Exception:
                pass

        # Directional overrides (see _T1 above): replace the market maker on these four products
        t1 = _T1()
        t1mem = mem.setdefault("t1", {})
        for p, strat in T1_STRAT.items():
            d = state.order_depths.get(p)
            if d is None or not d.buy_orders or not d.sell_orders:
                continue
            try:
                bb, ba = max(d.buy_orders), min(d.sell_orders)
                result[p] = getattr(t1, strat)(p, d, state.position.get(p, 0), T1_LIM[p], bb, ba,
                                               (bb + ba) / 2, t1mem.setdefault(p, {}), P[p])
            except Exception:
                pass

        # round stored floats to keep traderData small
        for k, v in list(mem.items()):
            if isinstance(v, float):
                mem[k] = round(v, 4)
        return result, 0, json.dumps(mem, separators=(",", ":"))
