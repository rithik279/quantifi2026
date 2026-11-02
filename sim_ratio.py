# Simulator for QuantiFi: generates new trading days that follow the same patterns as days -2..0,
# then scores a trader on them with backtester.py (same fill rules as the official site).
#
# Usage (same folder as backtester.py and datamodel.py):
#   python sim.py trader.py 100              100 normal days
#   python sim.py trader.py 30 tell_fewer    a stress test (see SCENARIOS at the bottom)
#
# Prints a profit summary, then risk-adjusted metrics. If the real price/trade CSVs are in the folder,
# it also runs the trader on the 3 real days (about 30 s) to compare out-of-sample with in-sample.
#
# Every day starts where day 0 ended, like Day 1 will. Day i always uses seed i, so two traders
# run with the same command see exactly the same days.

import sys
from collections import defaultdict

import numpy as np
from scipy.signal import lfilter
from scipy.special import ndtr


def tiers(base, width):
    return [(base + i * width, base + i * width + width - 1) for i in range(3)]


# Order book recipe: each side has 3 quote tiers at a random offset from fair value
# (tier 1 always shown, tiers 2 and 3 each shown 70% of the time).
# product: (offset range for each tier, volume range)
NARROW = [(1, 2), (3, 4), (5, 6)]
BOOK = {
    "AMETHYST": (NARROW, (5, 30)),
    "PAPER_LANTERNS": (NARROW, (5, 30)),
    "TOFFEE_CAKE": (tiers(6, 3), (5, 30)),
    "GOLDEN_PEARLS": (NARROW, (5, 25)),
    "PINK_PEARLS": (NARROW, (5, 25)),
    "WHITE_PEARLS": (NARROW, (5, 25)),
    "BLUE_PEARLS": (tiers(2, 2), (5, 25)),
    "BLACK_PEARLS": (tiers(3, 2), (5, 25)),
    "JELLY": (tiers(4, 3), (5, 25)),
    "PEANUT_BUTTER": (tiers(2, 2), (5, 25)),
    "DRAGONFRUIT": (NARROW, (5, 20)),
    "GRANADILLA": (NARROW, (5, 20)),
    "MANGOSTEEN": (NARROW, (5, 20)),
    "FRUIT_BASKET": (tiers(2, 2), (5, 20)),
    "LYCHEE": (NARROW, (10, 40)),
    "TELLURIUM": (tiers(3, 3), (5, 20)),
}
STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
for K in STRIKES:
    if K <= 7000:
        offsets = [(2, 3), (4, 5), (6, 7)]
    elif K <= 7750:
        offsets = [(1, 1), (2, 3), (4, 5)]
    else:
        offsets = [(1, 1), (2, 2), (3, 3)]
    BOOK[f"VOUCHER_{K}"] = (offsets, (5, 20))

# how much each voucher's implied vol wobbles around the smile
VOL_NOISE = dict(zip(STRIKES, np.array([2.53, 2.37, 2.03, 1.98, 1.88, 1.93, 2.01, 1.98, 2.18, 2.2]) * 1.05e-3))

# random (uninformed) market trades: (chance of a trade each tick, max size)
FLOW = {
    "AMETHYST": (.0143, 4), "PAPER_LANTERNS": (.0103, 4), "TOFFEE_CAKE": (.0045, 6),
    "GOLDEN_PEARLS": (.0059, 3), "PINK_PEARLS": (.0061, 3), "WHITE_PEARLS": (.0065, 3),
    "BLUE_PEARLS": (.0057, 3), "BLACK_PEARLS": (.0055, 3), "JELLY": (.0063, 4), "PEANUT_BUTTER": (.0065, 4),
    "DRAGONFRUIT": (.0019, 3), "GRANADILLA": (.0025, 3), "MANGOSTEEN": (.0019, 3), "FRUIT_BASKET": (.0016, 3),
    "LYCHEE": (.0058, 4),
}
TELLURIUM_SIZES = np.array([.06, .24, .21, .16, .12, .07, .06, .04, .03, .02])  # trade sizes 1..10

# The 28 real TELLURIUM jumps, each fitted as a damped spring:
# (jump size, target relative to the post-jump price in jump units, frequency, damping, starting speed)
TELLURIUM_JUMPS = [
    (77.5, 2.838, .013, .742, -.144), (106.5, .209, .006, .739, 1.181), (159.5, .870, .012, .458, .846),
    (126.5, .819, .008, .343, .556), (128, .225, .006, .894, 1.134), (260.5, -.631, .005, .531, -.638),
    (199.5, .388, .012, .662, 1.987), (190, .347, .011, .877, 4.294), (190.5, -1.751, .001, 5, -1.466),
    (126, .655, .008, .608, .404), (175.5, -.249, .007, .630, .602), (216, -.815, .005, .957, -1.643),
    (139.5, -.186, .011, .846, 3.350), (170.5, -.162, .007, .494, .686), (231.5, -.642, .017, 2.074, -1.709),
    (105, .169, .040, .173, -.283), (194, -1.234, .031, 1.942, -3.688), (102.5, 1.142, .007, .821, 1.170),
    (282.5, -.857, .017, 1.367, -3.092), (256, -.907, .016, 1.391, -3.245), (107, .204, .018, .173, -.232),
    (151.5, -.971, .011, 1.798, -2.564), (236, .075, .005, .768, .993), (157, .245, .007, .340, .593),
    (172.5, .724, .007, .600, 1.611), (300.5, -.846, .023, 2.348, -4.958), (199, .319, .009, .392, .531),
    (143.5, .808, .010, .572, .274),
]

# where day 0 ended
START = {
    "GOLDEN": 7750, "PINK": 9823.5, "TELL": 5134.5, "PAPER": 4881.5, "TOFFEE": 4985.0,
    "BLUE": 5595.0, "WHITE": 14649.5, "BLACK": 12184.0, "JELLY": 2090.0, "PB": 3438.0,
    "DF": 3601.5, "GR": 2095.5, "MG": 4230.0, "FB": 17511.0, "LYCHEE": 7405.5, "C": 0.0495,
}

DEFAULTS = dict(
    golden_dir=-1, golden_rate=1.0,               # GOLDEN slides: direction, slides per day
    pink_gap=160, pink_sum=True,                  # PINK: old random-jump model, or the 50,000 pearl-sum rule
    tell_gap=800, tell_w=1.0, tell_v0=1.0, tell_types="all",
    paper_vsd=.0576, paper_seg=500, paper_off=0, paper_noise=.96,
    toffee_mu=5003., toffee_th=.00476, toffee_sd=23.4, toffee_noise=1.23,
    vol_c=None, vol_scale=1.0, u_sd=1.0,          # voucher smile level and wobble
    start_jitter=0.0,                             # >0 randomizes the starting prices
    n=10000,
)


def ar1(n, a, sd, x0, rng):
    # x[t] = a * x[t-1] + sd * noise
    e = rng.standard_normal(n) * sd
    e[0] += a * x0
    return lfilter([1.0], [1.0, -a], e)


def ou(n, mu, theta, sd, x0, rng):
    # mean-reverting process with long-run standard deviation sd
    a = np.exp(-theta)
    return mu + ar1(n, a, sd * np.sqrt(1 - a * a), x0 - mu, rng)


def spring(k, x0, w, z, v0):
    # damped spring: distance from target after k ticks, starting at x0 with speed v0
    if z < 1:
        wd = w * np.sqrt(1 - z * z)
        return np.exp(-z * w * k) * (x0 * np.cos(wd * k) + (v0 + z * w * x0) / wd * np.sin(wd * k))
    s = np.sqrt(z * z - 1) + 1e-9
    r1, r2 = -w * (z - s), -w * (z + s)
    b = (v0 - r1 * x0) / (r2 - r1)
    return (x0 - b) * np.exp(r1 * k) + b * np.exp(r2 * k)


def tellurium_path(n, p0, cfg, rng):
    # quiet random walk, plus jumps every 150 + Exp(tell_gap) ticks. After each jump the price
    # follows one of the real jumps' spring shapes (randomly scaled a little)
    shapes = [s for s in TELLURIUM_JUMPS
              if cfg["tell_types"] == "all" or (s[1] > 0) == (cfg["tell_types"] == "cont")]
    smooth = np.full(n, float(p0))
    active = np.zeros(n, bool)
    jumps = []
    t = int(rng.exponential(cfg["tell_gap"]))
    while t < n:
        jumps.append(t)
        t += 150 + int(rng.exponential(cfg["tell_gap"]))
    for j, t0 in enumerate(jumps):
        t1 = jumps[j + 1] if j + 1 < len(jumps) else n
        size, target, w, z, v0 = shapes[rng.integers(len(shapes))]
        f = rng.uniform(.85, 1.15)
        size *= f
        sign = rng.choice((-1, 1))
        w *= rng.uniform(.85, 1.15) * cfg["tell_w"]
        z *= rng.uniform(.85, 1.15)
        target *= rng.uniform(.9, 1.1)
        p = smooth[t0 - 1] + sign * size if t0 else p0 + sign * size
        goal = p + sign * target * size
        k = np.arange(t1 - t0)
        smooth[t0:t1] = goal + spring(k, p - goal, w, z, sign * v0 * f * cfg["tell_v0"])
        active[t0 + 3:min(t1, t0 + 200)] = True  # busy period after a jump: wider book, heavy trading
    fair = smooth + np.cumsum(rng.standard_normal(n) * 0.7)
    return fair, active, np.gradient(smooth)


def call_price(S, K, vol):
    d1 = (np.log(S / K) + 0.5 * vol * vol) / vol
    return S * ndtr(d1) - K * ndtr(d1 - vol)


def fair_values(cfg, rng):
    # Hidden fair value of every product for one day. The order of the random draws matters
    # (it keeps each seed's day the same), so don't reorder these sections.
    n = cfg["n"]
    start = dict(START)
    if cfg["start_jitter"]:
        for key, sd in (("PINK", 50), ("TELL", 300), ("PAPER", 150), ("TOFFEE", 25), ("BLUE", 150),
                        ("WHITE", 220), ("BLACK", 220), ("JELLY", 300), ("PB", 450), ("DF", 200),
                        ("GR", 160), ("MG", 230), ("LYCHEE", 120)):
            start[key] += cfg["start_jitter"] * sd * rng.standard_normal()

    fv = {"AMETHYST": np.full(n, 10000.0)}

    # GOLDEN: flat integer level with rare straight slides of 50 or 100 over 50 ticks
    golden = np.full(n, float(start["GOLDEN"]))
    for _ in range(rng.poisson(cfg["golden_rate"])):
        t0 = rng.integers(0, n - 60)
        size = rng.choice((50, 100, 100))
        direction = cfg["golden_dir"] or rng.choice((-1, 1))
        golden[t0:] += direction * np.minimum(np.arange(n - t0) + 1, 50) * (size // 50)
    fv["GOLDEN_PEARLS"] = golden

    # PINK's random numbers are drawn here, but its path is built below, once the other pearls exist
    pink_jump = rng.random(n) < 1 / cfg["pink_gap"]
    pink_sign = rng.choice((-1, 1), n)
    pink_size = rng.uniform(6, 15, n)

    fv["TELLURIUM"], tell_active, tell_speed = tellurium_path(n, start["TELL"], cfg, rng)

    # PAPER: straight lines with a new slope every paper_seg ticks, plus noise
    seg = cfg["paper_seg"]
    n_seg = n // seg + 2
    slopes = np.empty(n_seg)
    slopes[0] = rng.normal(0, cfg["paper_vsd"])
    for j in range(1, n_seg):
        slopes[j] = .27 * slopes[j - 1] + np.sqrt(1 - .27 ** 2) * rng.normal(0, cfg["paper_vsd"])
    steps = np.repeat(np.clip(slopes, -.12, .12), seg)[cfg["paper_off"]:cfg["paper_off"] + n]
    fv["PAPER_LANTERNS"] = start["PAPER"] + np.cumsum(steps) + rng.standard_normal(n) * cfg["paper_noise"]

    # TOFFEE: snaps back to its mean, plus noise
    fv["TOFFEE_CAKE"] = (ou(n, cfg["toffee_mu"], cfg["toffee_th"], cfg["toffee_sd"], start["TOFFEE"], rng)
                         + rng.standard_normal(n) * cfg["toffee_noise"])

    # BLUE: random walk with short momentum. WHITE and BLACK move against BLUE and each other,
    # so WHITE + BLACK + BLUE barely moves
    a = np.exp(-1 / 5.1)
    momentum = ar1(n, a, 0.46 * np.sqrt(1 - a * a), 0, rng)
    blue_steps = momentum + rng.standard_normal(n) * np.sqrt(1.325)
    fv["BLUE_PEARLS"] = start["BLUE"] + np.cumsum(blue_steps)
    e = rng.multivariate_normal([0, 0], [[4.69, -4.36], [-4.36, 4.65]], n)
    fv["WHITE_PEARLS"] = start["WHITE"] + np.cumsum(-0.425 * blue_steps + e[:, 0])
    fv["BLACK_PEARLS"] = start["BLACK"] + np.cumsum(-0.437 * blue_steps + e[:, 1])

    # PINK: the five pearls sum to ~50,000. PINK stays put, then jumps exactly onto
    # 50,000 minus the other four once that gap passes a random 6-15
    target = 50000 - fv["WHITE_PEARLS"] - fv["BLACK_PEARLS"] - fv["BLUE_PEARLS"] - fv["GOLDEN_PEARLS"]
    if cfg["pink_sum"]:
        pink = np.empty(n)
        cur = target[0] + (start["PINK"] - (50000 - START["WHITE"] - START["BLACK"] - START["BLUE"] - START["GOLDEN"]))
        k = 0
        for i in range(n):
            if abs(target[i] - cur) > pink_size[k]:
                cur = target[i]
                k += 1
            pink[i] = cur
        fv["PINK_PEARLS"] = pink
    else:  # stress test: PINK jumps at random instead
        fv["PINK_PEARLS"] = start["PINK"] + np.cumsum(pink_jump * pink_sign * pink_size)

    # JELLY and PEANUT_BUTTER: correlated, slowly mean-reverting
    z = rng.multivariate_normal([0, 0], [[1, .68], [.68, 1]], n)
    for product, key, mu, theta, var, col in (("JELLY", "JELLY", 2000, 3e-4, 10.0, 0),
                                               ("PEANUT_BUTTER", "PB", 3300, 1.16e-3, 22.5, 1)):
        decay = np.exp(-theta)
        x = lfilter([1.0], [1.0, -decay], z[:, col] * np.sqrt(var))
        fv[product] = mu + (start[key] - mu) * decay ** np.arange(1, n + 1) + x

    # random walks
    for product, key, var in (("DRAGONFRUIT", "DF", 3.96), ("GRANADILLA", "GR", 2.63),
                              ("MANGOSTEEN", "MG", 5.65), ("LYCHEE", "LYCHEE", 1.45)):
        fv[product] = start[key] + np.cumsum(rng.standard_normal(n) * np.sqrt(var))

    # FRUIT_BASKET = 2 DRAGONFRUIT + 3 GRANADILLA + 1 MANGOSTEEN + a gap that wanders
    gap0 = start["FB"] - 2 * start["DF"] - 3 * start["GR"] - start["MG"]
    fv["FRUIT_BASKET"] = (2 * fv["DRAGONFRUIT"] + 3 * fv["GRANADILLA"] + fv["MANGOSTEEN"] + gap0
                          + np.cumsum(rng.standard_normal(n) * np.sqrt(18.5)))

    # vouchers: Black-Scholes on a smile, plus a separate slowly fading vol wobble per strike
    S = fv["LYCHEE"]
    level = (cfg["vol_c"] or start["C"]) + np.cumsum(rng.standard_normal(n) * 5e-5)
    wobble = {}
    a = 0.992
    for K in STRIKES:
        sd = VOL_NOISE[K] * cfg["u_sd"]
        wobble[K] = ar1(n, a, sd * np.sqrt(1 - a * a), rng.standard_normal() * sd, rng) / sd
        x = np.log(K / S)
        vol = np.maximum(0.003, cfg["vol_scale"] * (1.118 * x * x - 0.0512 * x + level) + wobble[K] * sd)
        fv[f"VOUCHER_{K}"] = call_price(S, K, vol)

    return fv, tell_active, tell_speed, wobble


def build_book(product, fair, rng, extra=None, narrow=None):
    # bid = floor(fair) - offset, ask = ceil(fair) + offset, for each of the 3 tiers
    n = len(fair)
    tier_offsets, (vol_lo, vol_hi) = BOOK[product]
    floor_fv, ceil_fv = np.floor(fair), np.ceil(fair)
    sides = []
    for side in (0, 1):
        levels = []
        for i, (lo, hi) in enumerate(tier_offsets):
            offset = rng.integers(lo, hi + 1, n).astype(float)
            if narrow is not None:  # TOFFEE's narrow-spread ticks: whole book 6 ticks closer
                offset = np.where(narrow, offset - 6, offset)
            if extra is not None:   # TELLURIUM's busy period: book wider by 0-3 ticks
                offset = offset + extra[side]
            price = floor_fv - offset if side == 0 else ceil_fv + offset
            shown = np.ones(n, bool) if i == 0 else rng.random(n) < 0.7
            if extra is None:
                volume = rng.integers(vol_lo, vol_hi + 1, n)
            else:
                volume = np.where(extra[2], rng.integers(2, 21, n), rng.integers(vol_lo, vol_hi + 1, n))
            levels.append((price, volume, shown))
        sides.append(levels)
    return sides


def market_trades(product, n, rng, tell_active, tell_speed, wobble):
    # returns (trade happens?, +1 buy at the ask / -1 sell at the bid, size) for every tick
    if product in FLOW:
        chance, max_size = FLOW[product]
        hit = rng.random(n) < chance
        side = rng.choice((-1, 1), n)
        size = rng.integers(1, max_size + 1, n)
    elif product == "TELLURIUM":  # busy after jumps, and mostly trades in the direction of the drift
        hit = rng.random(n) < np.where(tell_active, .37, .006)
        side = np.where(tell_active & (rng.random(n) < .76), np.sign(tell_speed).astype(int), rng.choice((-1, 1), n))
        side[side == 0] = 1
        size = rng.choice(np.arange(1, 11), n, p=TELLURIUM_SIZES / TELLURIUM_SIZES.sum())
    else:  # vouchers: traders buy when the voucher is cheap and sell when it's rich
        z = wobble[int(product.split("_")[1])]
        hit = rng.random(n) < np.minimum(.9, .075 * np.abs(z))
        side = np.where(rng.random(n) < 1 / (1 + np.exp(4 * z)), 1, -1)
        size = rng.integers(1, 4, n)
    return hit, side, size


def gen_day(seed=0, overrides=None, products=None):
    # one synthetic day in the same format backtester.load_day returns
    cfg = dict(DEFAULTS, **(overrides or {}))
    rng = np.random.default_rng(seed)
    n = cfg["n"]
    fv, tell_active, tell_speed, wobble = fair_values(cfg, rng)
    timestamps = [100 * i for i in range(n)]
    book = defaultdict(dict)
    trades = defaultdict(lambda: defaultdict(list))

    for product, fair in fv.items():
        if products and product not in products:
            continue
        extra = narrow = None
        if product == "TELLURIUM":
            extra = (np.where(tell_active, rng.integers(0, 4, n), 0),
                     np.where(tell_active, rng.integers(0, 4, n), 0), tell_active)
        if product == "TOFFEE_CAKE":  # narrow-spread ticks: start with prob .063, last with prob .265
            r = rng.random(n)
            narrow = np.zeros(n, bool)
            for i in range(1, n):
                narrow[i] = r[i] < (.265 if narrow[i - 1] else .063)
        sides = build_book(product, fair, rng, extra, narrow)
        best_ask = sides[1][0][0].astype(int)
        hit, side, size = market_trades(product, n, rng, tell_active, tell_speed, wobble)

        bid_levels = [(p.astype(int), v, s) for p, v, s in sides[0]]
        ask_levels = [(p.astype(int), v, s) for p, v, s in sides[1]]
        for i in range(n):
            bids = [(int(p[i]), int(v[i])) for p, v, s in bid_levels if s[i] and p[i] > 0]
            asks = [(int(p[i]), int(v[i])) for p, v, s in ask_levels if s[i]]
            if not bids:  # only possible for a near-worthless voucher
                bids = [(max(1, best_ask[i] - 2), 5)]
            book[timestamps[i]][product] = (bids, asks, (bids[0][0] + asks[0][0]) / 2)
            if hit[i]:
                price = asks[0][0] if side[i] > 0 else bids[0][0]
                trades[timestamps[i]][product].append((price, int(size[i])))
    return book, trades, timestamps


TELL = ["TELLURIUM"]
VOUCHER_PRODUCTS = ["LYCHEE"] + [f"VOUCHER_{K}" for K in STRIKES]
PEARLS = ["PINK_PEARLS", "WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "BLUE_PEARLS"]

# name: (settings changed, products simulated, None = all)
SCENARIOS = {
    "base": ({}, None),
    "golden_down3": ({"golden_rate": 3}, ["GOLDEN_PEARLS"]),
    "golden_up3": ({"golden_rate": 3, "golden_dir": 1}, ["GOLDEN_PEARLS"]),
    "toffee_mu+40": ({"toffee_mu": 5043}, ["TOFFEE_CAKE"]),
    "toffee_mu-40": ({"toffee_mu": 4963}, ["TOFFEE_CAKE"]),
    "tell_fewer": ({"tell_gap": 1600}, TELL),          # half as many jumps
    "tell_more": ({"tell_gap": 400}, TELL),            # twice as many jumps
    "tell_weak": ({"tell_w": .6, "tell_v0": .5}, TELL),
    "tell_cont": ({"tell_types": "cont"}, TELL),       # every drift continues
    "tell_rev": ({"tell_types": "rev"}, TELL),         # every drift reverses
    "paper_seg250": ({"paper_seg": 250}, ["PAPER_LANTERNS"]),
    "paper_seg1000": ({"paper_seg": 1000}, ["PAPER_LANTERNS"]),
    "paper_off250": ({"paper_off": 250}, ["PAPER_LANTERNS"]),
    "vol_low": ({"vol_scale": .85}, VOUCHER_PRODUCTS),
    "pink_nosum": ({"pink_sum": False}, PEARLS),
    "random_start": ({"start_jitter": 1.0}, None),
}

GROUPS = {
    "TELLURIUM": TELL,
    "Vouchers": VOUCHER_PRODUCTS[1:],
    "TOFFEE": ["TOFFEE_CAKE"],
    "PAPER": ["PAPER_LANTERNS"],
    "AMETH+GOLD+PINK": ["AMETHYST", "GOLDEN_PEARLS", "PINK_PEARLS"],
    "MM other 10": ["BLACK_PEARLS", "BLUE_PEARLS", "WHITE_PEARLS", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN",
                    "FRUIT_BASKET", "JELLY", "PEANUT_BUTTER", "LYCHEE"],
}


def max_drawdown(curve):
    # largest peak-to-trough fall of a running PnL curve that starts at 0
    curve = np.concatenate(([0.0], np.asarray(curve, float)))
    return float(np.max(np.maximum.accumulate(curve) - curve))


class FillCounter:
    # wraps a trader and counts our own fills (each tick the backtester reports the previous tick's fills)
    def __init__(self, trader):
        self.trader = trader
        self.fills = 0
        self.units = 0

    def run(self, state):
        for fills in state.own_trades.values():
            self.fills += len(fills)
            self.units += sum(t.quantity for t in fills)
        return self.trader.run(state)


def simulate(trader_path, n_days, overrides=None, products=None, out=None, seed0=0):
    import pandas as pd
    import backtester
    trader_class = backtester.load_trader(trader_path)
    rows = []
    for seed in range(seed0, seed0 + n_days):
        key = ("sim", seed)
        backtester._cache[key] = gen_day(seed, overrides, products)
        counter = FillCounter(trader_class())
        pnl, path, _ = backtester.run_day(counter, key, products=products)
        del backtester._cache[key]
        rows.append(dict(seed=seed, **pnl, max_dd=max_drawdown(path), fills=counter.fills, units=counter.units))
        if out:
            pd.DataFrame(rows).to_csv(out, index=False)  # saved every day, so a long run can be stopped early
    return pd.DataFrame(rows)


def in_sample(trader_path, products=None):
    # the same trader on the real days -2, -1, 0 (returns None if the CSVs aren't in this folder)
    import pandas as pd
    import backtester
    trader_class = backtester.load_trader(trader_path)
    rows = []
    for day in (-2, -1, 0):
        try:
            pnl, _, _ = backtester.run_day(trader_class(), day, products=products)
        except FileNotFoundError:
            return None
        rows.append(pnl)
    return pd.DataFrame(rows)


def group_pnl(df):
    import pandas as pd
    g = pd.DataFrame({name: df[[c for c in cols if c in df]].sum(axis=1)
                      for name, cols in GROUPS.items() if any(c in df for c in cols)})
    g["TOTAL"] = g.sum(axis=1)
    return g


def summary(df):
    import pandas as pd
    g = group_pnl(df)
    stats = {"mean": g.mean(), "sd": g.std(), "p5": g.quantile(.05), "min": g.min(), "loss%": (g < 0).mean() * 100}
    return pd.DataFrame(stats).round(0)


def risk_report(df, real=None):
    # all ratios use daily PnL across the simulated days (no risk-free rate, since PnL is in coins with no capital base)
    import pandas as pd
    rows = {}
    for name, x in group_pnl(df).items():
        x = x.to_numpy(float)
        sd = x.std(ddof=1) if len(x) > 1 else 0.0
        downside = np.sqrt(np.mean(np.minimum(x, 0) ** 2))
        gains, losses = x[x > 0].sum(), -x[x < 0].sum()
        var5 = np.percentile(x, 5)
        rows[name] = {
            "mean/day": x.mean(),
            "Sharpe/day": x.mean() / sd if sd > 0 else np.inf,
            "Sharpe ann.": x.mean() / sd * np.sqrt(252) if sd > 0 else np.inf,   # x sqrt(252 trading days)
            "Sortino/day": x.mean() / downside if downside > 0 else np.inf,
            "profit factor": gains / losses if losses > 0 else np.inf,
            "win days %": 100 * np.mean(x > 0),
            "VaR 5%": var5,                    # 1 day in 20 is worse than this
            "CVaR 5%": x[x <= var5].mean(),    # average of the worst 5% of days
        }
    table = pd.DataFrame(rows).T
    if real is not None:
        table["in-sample/day"] = group_pnl(real).mean()
        table["OOS/IS"] = table["mean/day"] / table["in-sample/day"]
    coins = [c for c in ("mean/day", "VaR 5%", "CVaR 5%", "in-sample/day") if c in table]
    return table.round(2).round({c: 0 for c in coins})


def totals_report(df):
    total = group_pnl(df)["TOTAL"]
    return "\n".join([
        f"days simulated (sample size): {len(df)}",
        f"our fills: {df['fills'].sum():,} total, {df['fills'].mean():,.0f} per day ({df['units'].mean():,.0f} units per day)",
        f"intraday max drawdown: median {df['max_dd'].median():,.0f}, worst {df['max_dd'].max():,.0f}",
        f"max drawdown of cumulative PnL across all days: {max_drawdown(np.cumsum(total)):,.0f}",
    ])


if __name__ == "__main__":
    name = sys.argv[3] if len(sys.argv) > 3 else "base"
    overrides, products = SCENARIOS[name]
    results = simulate(sys.argv[1], int(sys.argv[2]), overrides, products, out=f"sim_{name}.csv")
    print(summary(results).to_string())
    real = in_sample(sys.argv[1], products) if name == "base" else None
    print("\nRisk-adjusted metrics (per simulated day, inf = no losing days):")
    print(risk_report(results, real).to_string())
    print()
    print(totals_report(results))
