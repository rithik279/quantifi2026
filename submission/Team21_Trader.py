"""
FINAL SUBMISSION (v10, Nov 1): teammate v7_2 (official ~484k) + trader_4 JELLY/PEANUT_BUTTER quoter
+ adaptive pearl "closer" detector (sum signal follows whichever pearl closes the 50,000 gap). Local 487,376.
QuantiFi 2026 trader: one Trader class, four strategy families.

  1. Single products  (AMETHYST, JELLY, PEANUT_BUTTER; TELLURIUM uses the post-jump strategy in _T1;
     TOFFEE_CAKE and PAPER_LANTERNS use the teammate's FrStandalone market makers, merged in v5)
     Inventory-skewed market maker (RCFA lineage): estimate fair value, take any quote that is
     clearly mispriced, then quote inside the spread with prices shifted against our inventory,
     and widen when the market gets jumpy.
  2. Basket family    (FRUIT_BASKET = 2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN)
     Hedged premium position vs a fixed anchor of 0 (teammate's FrBasket, merged in v5).
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
CLOSER_H, CLOSER_SPAN, CLOSER_WARMUP, CLOSER_THR, CLOSER_KEEP = 20, 3000, 1000, -0.25, -0.1   # v9 adaptive sum-rule closer

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
    "OPTIONS": {"edge": 2, "take": 3, "skew": 0, "smile_span": 50, "shade": 0.0, "min_points": 5, "flow_k": 0.0, "flow_decay": 0.9},
    "WHITE_PEARLS": {"fair": "ema", "edge": 4, "take": 5, "skew": 0, "vol_k": 0.0, "span": 5},
    "BLACK_PEARLS": {"fair": "ema", "edge": 2, "take": 3, "skew": 3, "vol_k": 0.0, "span": 5},
    "BLUE_PEARLS": {"fair": "ema", "edge": 4, "take": 5, "skew": 3, "vol_k": 0.0, "span": 5},
    "PINK_PEARLS": {"fair": "mid", "edge": 0, "take": 3, "skew": 3, "vol_k": 0.0, "alpha": 0.8, "guard": 40.0},
}

SINGLES = ["AMETHYST"]   # JELLY, PEANUT_BUTTER: tiny EMA quoter in Trader.run (v10, from trader_4)   # TOFFEE_CAKE, PAPER_LANTERNS, TELLURIUM: see _T1


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
#                    (wait 20 ticks to confirm direction, hold to tick 250). v7.1 adds the teammate's guard:
#                    every signal is paper-traded; new trades are skipped while fewer than 3 of the last 6
#                    signals made money. Identical on the training days; if the post-jump drift reverses
#                    on every jump (stress test) it cuts the loss from -101.7k to -59.4k.
#   GOLDEN_PEARLS  : quote around the current plateau; ride the slides between plateaus
# =========================================================================================
from math import erf as _erf
T1_LIM = {'TELLURIUM': 40, 'GOLDEN_PEARLS': 20}
P = {
    'GOLDEN_PEARLS': {'jump': 3, 'ramp': 3, 'stall': 8},
    'TELLURIUM': {'jump': 25, 'jk': 5.5, 'w': 20, 'H': 250, 'guard': {'n': 6, 'min_wins': 3}},
}
QMAX = 5
T1_STRAT = {'GOLDEN_PEARLS': 'level', 'TELLURIUM': 'jumpdrift'}   # TOFFEE/PAPER: see FrStandalone

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
        g = prm.get('guard')

        def close_paper():
            # Guard (teammate's design): every signal is also paper-traded at the touch, live or not.
            if m.get('pd'):
                ex = bb if m['pd'] > 0 else ba
                m['out'] = (m.get('out', []) + [m['pd'] * (ex - m['pe'])])[-(g['n'] if g else 1):]
                m['pd'] = 0
        if len(h) == 4 and abs(h[-1] - h[0]) > thr and (k < 0 or k > 5):
            k = 0; m['ref'] = None; close_paper()
        elif k >= 0: k += 1
        if k == 3: m['ref'] = mid
        tgt = 0
        if prm['w'] <= k <= prm['H'] and m.get('ref') is not None:
            if k == prm['w']:
                m['dir'] = 1 if mid > m['ref'] else -1 if mid < m['ref'] else 0
                out = m.get('out', [])
                # trade the new signal only if at least min_wins of the last n paper signals made money
                m['on'] = (not g) or len(out) < g['n'] or sum(x > 0 for x in out) >= g['min_wins']
                if m['dir']:
                    m['pd'], m['pe'] = m['dir'], (ba if m['dir'] > 0 else bb)
            tgt = m.get('dir', 0) * L if m.get('on', True) else 0
        elif k > prm['H']:
            k = -1; close_paper()
        m['k'] = k; self.to_target(p, d, tgt, pos, L, o); return o






# =========================================================================================
# Merged from the teammate's Team #21 trader (trader__1_.py). Each beat our own logic on every
# training day AND across a neighbourhood of nearby settings (robustness grids):
#   TOFFEE_CAKE    : market making around 50% fast EMA + 50% anchor at 5,000 (gated adaptive anchor);
#                    v7 settings (anchor weight 0.4, take 9, span 5, skew 1) chosen out of sample: they beat
#                    v6 on the held-out day in all three leave-one-day-out folds (+6.1k)
#                    27/27 nearby settings positive every day; worst 63.0k vs our old 53.8k
#   PAPER_LANTERNS : market making around an EMA extrapolated along its own slope (trend-aware fair)
#                    27/27 positive every day; 22/27 beat our old 48.7k
#   Basket family  : hold a hedged premium position (basket vs 2D+3G+1M) proportional to its distance
#                    from 0 (fair value of a basket = its contents); 9/9 hedged settings beat our old
#                    3.1k; UNHEDGED versions lose up to 40k, so the hedge is essential
# =========================================================================================
STANDALONE_LIMITS = {"AMETHYST": 50, "TOFFEE_CAKE": 50, "PAPER_LANTERNS": 50, "TELLURIUM": 40, "JELLY": 50, "PEANUT_BUTTER": 50}

# fair: "fixed" uses `value`; "ema" uses an EMA of the mid with `span`; "mid" uses the current mid;
#       "trend" = EMA + its slope over `slope_window` ticks, extrapolated `lead` ticks ahead.
# anchor/anchor_w: pull the fair value toward a long-run level (mean reversion).
# anchor_span: if set, the anchor itself is re-estimated as a slow EMA of the mid starting at `anchor`.
# flow_beta/flow_decay: shift fair value by recent signed aggressor volume (informed flow).
# soft_cap: max |position| we build (the hard limit still applies).
# glide (TELLURIUM): after a jump of >= J coins within 5 ticks, wait W ticks; if the price has moved
#   >= gmin since the jump, take the full limit in that direction ("ride the glide") and hold until the
#   last K-tick move stalls below `flat` (or after H ticks); then flatten ("take") or hand back to market
#   making ("mm"). Market making runs whenever no glide trade is on. See notebooks/weak/NOTES.md.
# take_edge=100 effectively disables taking. Choices are explained in notebooks/standalone/NOTES.md.
STANDALONE_GLIDE = dict(J=60, W=20, gmin=15, K=20, flat=0.0, H=300, cool=50, exit="take")
STANDALONE_PARAMS_ALL: Dict[str, dict] = {
    "AMETHYST":       dict(fair="fixed", value=10_000, take_edge=1, make_edge=1, skew=0),
    "TOFFEE_CAKE":    dict(fair="ema", span=5, anchor=5_000, anchor_w=0.4, take_edge=9, make_edge=2, skew=1,
                           anchor_span=2000, anchor_gate=20),  # gated adaptive anchor, notebooks/adaptive/NOTES.md
    "PAPER_LANTERNS": dict(fair="trend", span=15, slope_window=50, lead=100, take_edge=1, make_edge=1, skew=1),
    "TELLURIUM":      dict(fair="mid", flow_beta=0.8, flow_decay=0.9, take_edge=100, make_edge=3, skew=5, soft_cap=15,
                           glide=STANDALONE_GLIDE),
    "JELLY":          dict(fair="mid", take_edge=100, make_edge=1, skew=0, soft_cap=3),
    "PEANUT_BUTTER":  dict(fair="mid", take_edge=100, make_edge=3, skew=5, soft_cap=10),
}


class FrStandalone:
    def __init__(self, params: Dict[str, dict] = None):
        self.params = params if params is not None else FR_SA_PARAMS

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
            anchor = prm["anchor"]
            if prm.get("anchor_span"):
                # adaptive anchor: a slow EMA of the mid that STARTS at the historical value, so it
                # stays near 5,000 if that still holds but follows the centre if it has moved
                a = 2 / (prm["anchor_span"] + 1)
                est = a * mid + (1 - a) * pm.get("anchor_est", prm["anchor"])
                pm["anchor_est"] = est
                # anchor_gate: keep the historical value until the estimate has clearly moved away
                # (a change detector), so nothing is lost while the old anchor still holds
                gate = prm.get("anchor_gate", 0)
                anchor = est if abs(est - prm["anchor"]) > gate else prm["anchor"]
            fair = (1 - prm["anchor_w"]) * fair + prm["anchor_w"] * anchor

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
        limit = STANDALONE_LIMITS[product]
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
                sig = self.glide_signal(mid, mem[product], prm["glide"], STANDALONE_LIMITS[product])
                if sig == "exit" and prm["glide"]["exit"] == "take":
                    result[product] = self.take_to(product, depth, position, 0)
                    continue
                if sig is not None and sig != "exit":
                    result[product] = self.take_to(product, depth, position, sig)
                    continue
            result[product] = self.make_orders(product, depth, position, fair)
        return result, 0, json.dumps(mem)



FR_SA_PARAMS = {p: STANDALONE_PARAMS_ALL[p] for p in ("TOFFEE_CAKE", "PAPER_LANTERNS")}

BASKET_BASKET = "FRUIT_BASKET"
BASKET_LIMITS = {BASKET_BASKET: 40, "DRAGONFRUIT": 40, "GRANADILLA": 40, "MANGOSTEEN": 40}

BASKET_PARAMS = dict(
    anchor=0.0,        # premium level the spread is pulled toward
    scale=1000.0,      # premium deviation at which we hold the full position
    max_baskets=40,    # 40 unhedged; hedged is capped at 13 by GRANADILLA's limit (3 x 13 = 39)
    hedge=True,
    min_trade=4,       # don't rebalance for less than this many baskets (1 over-trades and loses every day)
)


def _basket_mid(d: OrderDepth) -> float:
    return (max(d.buy_orders) + min(d.sell_orders)) / 2


def _basket_move_to(product: str, depth: OrderDepth, position: int, target: int, limit: int) -> List[Order]:
    """Cross the book toward `target`, never past the position limit."""
    target = max(-limit, min(limit, target))
    diff = target - position
    orders: List[Order] = []
    if diff > 0:
        for ask in sorted(depth.sell_orders):
            if diff <= 0:
                break
            q = min(diff, -depth.sell_orders[ask])
            orders.append(Order(product, ask, q)); diff -= q
    elif diff < 0:
        for bid in sorted(depth.buy_orders, reverse=True):
            if diff >= 0:
                break
            q = min(-diff, depth.buy_orders[bid])
            orders.append(Order(product, bid, -q)); diff += q
    return orders


class FrBasket:
    def __init__(self, params: dict = None):
        self.params = dict(BASKET_PARAMS, **(params or {}))

    def run(self, state: TradingState):
        prm = self.params
        names = [BASKET_BASKET] + list(BASKET_WEIGHTS)
        depths = {p: state.order_depths.get(p) for p in names}
        if any(d is None or not d.buy_orders or not d.sell_orders for d in depths.values()):
            return {}, 0, state.traderData
        mids = {p: _basket_mid(d) for p, d in depths.items()}
        premium = mids[BASKET_BASKET] - sum(w * mids[p] for p, w in BASKET_WEIGHTS.items())

        max_b = prm["max_baskets"]
        if prm["hedge"]:
            max_b = min(max_b, min(BASKET_LIMITS[p] // w for p, w in BASKET_WEIGHTS.items()))
        dev = (premium - prm["anchor"]) / prm["scale"]
        target = int(round(-max(-1.0, min(1.0, dev)) * max_b))

        pos_b = state.position.get(BASKET_BASKET, 0)
        result: Dict[str, List[Order]] = {}
        if abs(target - pos_b) >= prm["min_trade"]:
            result[BASKET_BASKET] = _basket_move_to(BASKET_BASKET, depths[BASKET_BASKET], pos_b, target, BASKET_LIMITS[BASKET_BASKET])
        if prm["hedge"]:
            # hedge the basket position we actually hold (fills come next tick)
            for p, w in BASKET_WEIGHTS.items():
                tgt = -w * pos_b
                pos = state.position.get(p, 0)
                if tgt != pos:
                    result[p] = _basket_move_to(p, depths[p], pos, tgt, BASKET_LIMITS[p])
        return result, 0, json.dumps({"premium": premium})



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
            # v7.2: flow_k = 0 (nudge OFF). The official backtester delivers state.market_trades differently
            # from our replica (portal voucher PnL matches a replica whose trade list includes our own fills
            # or is not cleared each tick), which turned this nudge from +2.8k into roughly -30k. With the
            # nudge off, no strategy reads market_trades, so results no longer depend on that delivery.
            # Informed flow: in this data a buyer-initiated voucher trade is followed by a ~7-coin higher
            # price 100 ticks later than a seller-initiated one. Nudge fair value toward recent signed
            # volume so we stop leaning against informed traders (Glosten-Milgrom / Kyle intuition).
            vm = mid_price(ods[sym])
            pv = mem.setdefault("pv", {}); vf = mem.setdefault("vf", {})
            prev = pv.get(sym, vm); sg = 0
            for tr in state.market_trades.get(sym, []):
                sg += tr.quantity if tr.price > prev else (-tr.quantity if tr.price < prev else 0)
            vf[sym] = round(vf.get(sym, 0.0) * op["flow_decay"] + sg, 3)
            pv[sym] = vm
            fair += op["flow_k"] * vf[sym]
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

        # v9: which pearl closes the gap? Online slope of each pearl's 20-tick change on the sum
        # deviation 20 ticks earlier (past data only). On days -2..0 PINK is -0.35..-0.41 every day and
        # every other pearl is within -0.07..+0.09, so the -0.2 threshold separates them cleanly.
        # PINK is the prior until enough ticks are seen; if no pearl clears the threshold, nobody gets
        # the sum signal and all pearls fall back to plain market making.
        ring = mem.setdefault("pq", [])
        ring.append([round(sum_dev, 1)] + [mids[p] for p in PEARLS])
        if len(ring) > CLOSER_H + 1:
            ring.pop(0)
        if len(ring) == CLOSER_H + 1:
            d0 = ring[0][0]
            mem["pq_xx"] = ema(mem.get("pq_xx"), d0 * d0, CLOSER_SPAN)
            for i, p in enumerate(PEARLS):
                mem["pq_" + p] = ema(mem.get("pq_" + p), (ring[-1][i + 1] - ring[0][i + 1]) * d0, CLOSER_SPAN)
            mem["pq_n"] = mem.get("pq_n", 0) + 1
        closer = "PINK_PEARLS"
        if mem.get("pq_n", 0) >= CLOSER_WARMUP and mem.get("pq_xx", 0) > 1e-9:
            beta = {p: mem["pq_" + p] / mem["pq_xx"] for p in PEARLS if p != "GOLDEN_PEARLS"}
            if beta.get(mem.get("closer", closer), 0.0) < CLOSER_KEEP:
                closer = mem.get("closer", closer)          # keep the current closer while it still works
            else:
                best = min(beta, key=beta.get)
                closer = best if beta[best] < CLOSER_THR else None
        mem["closer"] = closer

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

            if p == "PINK_PEARLS" and closer != p:
                prm = self.params["BLACK_PEARLS"]                 # demoted: plain EMA market maker
                fair = self.basic_fair("PINK_ALT", od, prm, mem)
            if p == closer:
                # The closer is the pearl that closes gaps in the 50,000 sum rule. Guardrail: if the
                # sum drifts far from 50,000 for a sustained period, the rule has broken and we
                # fall back to plain market making.
                prm = self.params["PINK_PEARLS"]
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
        for fn in (self.trade_singles, self.trade_options, self.trade_pearls):   # basket: see FrBasket
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

        # Teammate's groups (own memory slots inside traderData, like their combined Trader).
        # v7: every float stored in traderData is rounded to 3 decimals (traderData 3.3k -> 2.3k characters).
        def _rnd(x):
            if isinstance(x, float): return round(x, 3)
            if isinstance(x, dict): return {k: _rnd(v) for k, v in x.items()}
            if isinstance(x, list): return [_rnd(v) for v in x]
            return x
        saved = state.traderData
        for name, grp in (("fr_sa", FrStandalone()), ("fr_bk", FrBasket())):
            state.traderData = mem.get(name, "")
            try:
                o, _, data = grp.run(state)
                if data:
                    data = json.dumps(_rnd(json.loads(data)), separators=(",", ":"))
                mem[name] = data or ""
                for p, ol in o.items():
                    result[p] = ol
            except Exception:
                pass
        state.traderData = saved

        # v10 (from trader_4): JELLY and PEANUT_BUTTER are random walks with no edge we could prove. Quote
        # 5 lots at the touch around a 5-tick EMA, only on the side where the touch is beyond fair, and
        # stop adding once |position| reaches 5% of the limit. Local: +3.3k vs our previous version.
        for p in ("JELLY", "PEANUT_BUTTER"):
            d = state.order_depths.get(p)
            if d is None or not d.buy_orders or not d.sell_orders:
                continue
            try:
                bb, ba = max(d.buy_orders), min(d.sell_orders)
                f = ema(mem.get("q_" + p), (bb + ba) / 2, 5)
                mem["q_" + p] = f
                pos, lim = state.position.get(p, 0), LIMITS[p]
                o = []
                if bb < f and pos < 0.05 * lim:
                    o.append(Order(p, bb, min(5, lim - pos)))
                if ba > f and pos > -0.05 * lim:
                    o.append(Order(p, ba, -min(5, lim + pos)))
                result[p] = o
            except Exception:
                pass

        # round stored floats to keep traderData small
        for k, v in list(mem.items()):
            if isinstance(v, float):
                mem[k] = round(v, 4)
            elif k == "t1":
                mem[k] = _rnd(v)
        return result, 0, json.dumps(mem, separators=(",", ":"))
