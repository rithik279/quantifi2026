"""Synthetic out-of-sample days made by editing the REAL days ("what might the judges change?").

Each scenario edits one day's prices and trades together, so the real order-book shapes and trade
flow are kept and only the thing we want to stress changes. Prices stay integers, so the backtester's
fill rule still applies exactly.

Use:   backtester.backtest(Trader, scenario="toffee_+50")
List:  python src/scenarios.py

Editing tools (each works on one product):
  shift    add a per-tick integer offset to the book and the trades (level shifts, drifts, regime breaks)
  mirror   price -> 2C - price, bids <-> asks, buyers <-> sellers (same statistics, opposite direction)
  vol      stretch or shrink moves around a smoothed path
  widen    push bids and asks k ticks further apart (trades at the touch move with them)
  reprice  options: move LYCHEE and/or change implied vol, re-pricing each voucher with Black-Scholes
  bootstrap  reorder 2,500-tick blocks of the day (non-option products together)
"""

from typing import Callable, Dict, Tuple

import numpy as np
import pandas as pd

TICKS = 10_000
PRICE_COLS = [f"{s}_price_{i}" for s in ("bid", "ask") for i in (1, 2, 3)]
STRIKES = [6800, 7000, 7200, 7300, 7400, 7500, 7600, 7750, 7900, 8100]
VOUCHERS = [f"VOUCHER_{k}" for k in STRIKES]
OPTION_PRODUCTS = ["LYCHEE"] + VOUCHERS
STANDALONE = ["AMETHYST", "TOFFEE_CAKE", "PAPER_LANTERNS", "TELLURIUM", "JELLY", "PEANUT_BUTTER"]
PEARLS = ["WHITE_PEARLS", "BLACK_PEARLS", "GOLDEN_PEARLS", "PINK_PEARLS", "BLUE_PEARLS"]
BASKET_GROUP = ["FRUIT_BASKET", "DRAGONFRUIT", "GRANADILLA", "MANGOSTEEN"]
NON_OPTION = STANDALONE + PEARLS + BASKET_GROUP

# Mirror centres (2C, so prices stay integers), from the 3-day mean mids. Chosen so the mirror keeps
# our known structure: AMETHYST and TOFFEE keep their anchors, the five pearl centres sum to exactly
# 50,000 (so the sum rule survives), and the basket centre equals 2D + 3G + 1M (so premium -> -premium).
MIRROR_2C = {
    "AMETHYST": 20_000, "TOFFEE_CAKE": 10_000, "PAPER_LANTERNS": 9_826, "TELLURIUM": 8_895,
    "JELLY": 3_952, "PEANUT_BUTTER": 6_743,
    "WHITE_PEARLS": 29_831, "BLACK_PEARLS": 24_015, "GOLDEN_PEARLS": 15_841, "PINK_PEARLS": 19_811,
    "BLUE_PEARLS": 10_502,
    "DRAGONFRUIT": 6_597, "GRANADILLA": 4_025, "MANGOSTEEN": 8_267,
}
MIRROR_2C["FRUIT_BASKET"] = 2 * MIRROR_2C["DRAGONFRUIT"] + 3 * MIRROR_2C["GRANADILLA"] + MIRROR_2C["MANGOSTEEN"]


# =========================
# Editing tools
# =========================
def _ticks(df: pd.DataFrame) -> np.ndarray:
    return (df["timestamp"] // 100).to_numpy()


def mid_path(prices: pd.DataFrame, product: str) -> np.ndarray:
    g = prices[prices["product"] == product].sort_values("timestamp")
    out = np.full(TICKS, np.nan)
    out[_ticks(g)] = g["mid_price"].to_numpy()
    return out


def shift(prices, trades, product, delta: np.ndarray):
    """Add delta[tick] (integers) to every price of `product`, book and trades alike."""
    m = (prices["product"] == product).to_numpy()
    d = delta[_ticks(prices[m])]
    for c in PRICE_COLS + ["mid_price"]:
        prices.loc[m, c] = prices.loc[m, c].to_numpy() + d
    mt = (trades["symbol"] == product).to_numpy()
    trades.loc[mt, "price"] = trades.loc[mt, "price"].to_numpy() + delta[_ticks(trades[mt])]


def mirror(prices, trades, product, two_c: int):
    m = (prices["product"] == product).to_numpy()
    sub = prices.loc[m].copy()
    for i in (1, 2, 3):
        prices.loc[m, f"bid_price_{i}"] = two_c - sub[f"ask_price_{i}"].to_numpy()
        prices.loc[m, f"bid_volume_{i}"] = sub[f"ask_volume_{i}"].to_numpy()
        prices.loc[m, f"ask_price_{i}"] = two_c - sub[f"bid_price_{i}"].to_numpy()
        prices.loc[m, f"ask_volume_{i}"] = sub[f"bid_volume_{i}"].to_numpy()
    prices.loc[m, "mid_price"] = two_c - sub["mid_price"].to_numpy()
    mt = (trades["symbol"] == product).to_numpy()
    trades.loc[mt, "price"] = two_c - trades.loc[mt, "price"].to_numpy()


def vol(prices, trades, product, factor: float, window: int = 201):
    """Scale moves around a centred rolling mean by `factor` (shifting whole ticks, spreads unchanged)."""
    mid = pd.Series(mid_path(prices, product)).ffill().bfill()
    smooth = mid.rolling(window, center=True, min_periods=1).mean()
    delta = np.round((smooth + factor * (mid - smooth) - mid).to_numpy()).astype(int)
    shift(prices, trades, product, delta)
    return delta


def widen(prices, trades, product, k: int):
    book = prices[prices["product"] == product][["timestamp", "bid_price_1", "ask_price_1"]]
    mt = (trades["symbol"] == product).to_numpy()
    tb = trades.loc[mt, ["timestamp", "price"]].merge(book, on="timestamp", how="left")
    side = np.select([tb.price >= tb.ask_price_1, tb.price <= tb.bid_price_1], [1, -1], 0)
    trades.loc[mt, "price"] = trades.loc[mt, "price"].to_numpy() + k * side
    m = (prices["product"] == product).to_numpy()
    for i in (1, 2, 3):
        prices.loc[m, f"bid_price_{i}"] -= k
        prices.loc[m, f"ask_price_{i}"] += k


def _ncdf(x):
    from scipy.stats import norm
    return norm.cdf(x)


def _bs(S, K, T, sig):
    sq = sig * np.sqrt(T)
    d1 = (np.log(S / K) + 0.5 * sq * sq) / sq
    return S * _ncdf(d1) - K * _ncdf(d1 - sq)


def _iv(price, S, K, T):
    lo, hi = np.full(price.shape, 1e-4), np.full(price.shape, 0.2)
    for _ in range(50):
        mid = (lo + hi) / 2
        high = _bs(S, K, T, mid) > price
        hi, lo = np.where(high, mid, hi), np.where(high, lo, mid)
    iv = (lo + hi) / 2
    bad = (price <= np.maximum(S - K, 0) + 1e-9) | (iv > 0.1999)
    return np.where(bad, np.nan, iv)


def reprice_options(prices, trades, day: int, lychee_delta: np.ndarray = None, iv_mult: float = 1.0):
    """Move LYCHEE by lychee_delta[tick] and/or scale implied vol; re-price every voucher's book and
    trades by the Black-Scholes change in its value (rounded to whole ticks)."""
    S = pd.Series(mid_path(prices, "LYCHEE")).ffill().bfill().to_numpy()
    dS = lychee_delta if lychee_delta is not None else np.zeros(TICKS, dtype=int)
    T = 8 - (day + 2) - np.arange(TICKS) * 100 / 1e6
    for k, v in zip(STRIKES, VOUCHERS):
        old = pd.Series(mid_path(prices, v)).ffill().bfill().to_numpy()
        iv = pd.Series(_iv(old, S, k, T)).ffill().bfill().fillna(0.02).to_numpy()
        new = _bs(S + dS, k, T, iv * iv_mult)
        shift(prices, trades, v, np.round(new - _bs(S, k, T, iv)).astype(int))
    if lychee_delta is not None:
        shift(prices, trades, "LYCHEE", dS)


def bootstrap(prices, trades, seed: int, block: int = 2_500, products=NON_OPTION):
    """Reorder whole blocks of the day (sampled with replacement) for `products`, keeping levels
    as they were, so there are small jumps at the joins. Options are left alone (their prices
    depend on time to expiry)."""
    rng = np.random.default_rng(seed)
    n = TICKS // block
    order = rng.integers(0, n, size=n)
    pm = prices["product"].isin(products).to_numpy()
    tm = trades["symbol"].isin(products).to_numpy()
    p_keep, t_keep = prices[~pm], trades[~tm]
    p_src, t_src = prices[pm], trades[tm]
    p_parts, t_parts = [p_keep], [t_keep]
    for b, ob in enumerate(order):
        for src, parts in ((p_src, p_parts), (t_src, t_parts)):
            tk = _ticks(src)
            s = src[(tk >= ob * block) & (tk < (ob + 1) * block)].copy()
            s["timestamp"] = (_ticks(s) - ob * block + b * block) * 100
            parts.append(s)
    return pd.concat(p_parts, ignore_index=True), pd.concat(t_parts, ignore_index=True)


# =========================
# Scenarios
# =========================
def _const(v):
    return np.full(TICKS, v, dtype=int)


def _from_midday(v):
    d = np.zeros(TICKS, dtype=int)
    d[TICKS // 2:] = v
    return d


def _ramp(total):
    return np.round(np.linspace(0, total, TICKS)).astype(int)


def _random_walk(seed, sigma):
    rng = np.random.default_rng(seed)
    return np.round(np.cumsum(rng.normal(0, sigma, TICKS))).astype(int)


def _sc_mirror(p, t, day):
    for prod, two_c in MIRROR_2C.items():
        mirror(p, t, prod, two_c)
    return p, t


def _sc_vol(factor):
    def f(p, t, day):
        for prod in NON_OPTION:
            vol(p, t, prod, factor)
        return p, t
    return f


def _sc_widen(p, t, day):
    for prod in NON_OPTION:
        widen(p, t, prod, 1)
    return p, t


def _sc_shift(product, delta_fn):
    def f(p, t, day):
        shift(p, t, product, delta_fn())
        return p, t
    return f


def _sc_lychee_vol(factor):
    def f(p, t, day):
        S = pd.Series(mid_path(p, "LYCHEE")).ffill().bfill()
        smooth = S.rolling(201, center=True, min_periods=1).mean()
        dS = np.round((smooth + factor * (S - smooth) - S).to_numpy()).astype(int)
        reprice_options(p, t, day, lychee_delta=dS)
        return p, t
    return f


def _sc_iv(mult):
    def f(p, t, day):
        reprice_options(p, t, day, iv_mult=mult)
        return p, t
    return f


def _sc_bootstrap(seed):
    def f(p, t, day):
        return bootstrap(p, t, seed=seed * 10 + day + 2)
    return f


SCENARIOS: Dict[str, Tuple[str, Callable]] = {
    "real": ("unchanged real data (sanity check)", lambda p, t, d: (p, t)),
    # anchors moved
    "toffee_+25": ("TOFFEE_CAKE centre 5,025 instead of 5,000", _sc_shift("TOFFEE_CAKE", lambda: _const(25))),
    "toffee_+50": ("TOFFEE_CAKE centre 5,050", _sc_shift("TOFFEE_CAKE", lambda: _const(50))),
    "toffee_-50": ("TOFFEE_CAKE centre 4,950", _sc_shift("TOFFEE_CAKE", lambda: _const(-50))),
    "toffee_+50_midday": ("TOFFEE_CAKE centre jumps to 5,050 halfway through the day", _sc_shift("TOFFEE_CAKE", lambda: _from_midday(50))),
    "toffee_drift_+100": ("TOFFEE_CAKE centre drifts from 5,000 to 5,100 over the day", _sc_shift("TOFFEE_CAKE", lambda: _ramp(100))),
    "amethyst_+5": ("AMETHYST worth 10,005 instead of 10,000", _sc_shift("AMETHYST", lambda: _const(5))),
    # structural relationships changed
    "pearls_sum_+100": ("pearls sum to 50,100 (WHITE shifted up)", _sc_shift("WHITE_PEARLS", lambda: _const(100))),
    "pearls_sum_+100_midday": ("pearl sum target jumps to 50,100 halfway through", _sc_shift("WHITE_PEARLS", lambda: _from_midday(100))),
    "basket_premium_+300": ("basket premium centred on +300 instead of 0", _sc_shift("FRUIT_BASKET", lambda: _const(300))),
    "basket_premium_rw": ("basket premium wanders freely (random walk added to the basket)", lambda p, t, d: (shift(p, t, "FRUIT_BASKET", _random_walk(d + 7, 3.0)), (p, t))[1]),
    # whole-market changes
    "mirror": ("every non-option product mirrored: trends reversed, anchors and rules kept", _sc_mirror),
    "vol_x1.5": ("all non-option products 50% more volatile", _sc_vol(1.5)),
    "vol_x0.6": ("all non-option products 40% calmer", _sc_vol(0.6)),
    "spread_+1": ("every non-option book one tick wider on each side", _sc_widen),
    # options
    "lychee_vol_x1.5": ("LYCHEE 50% more volatile, vouchers re-priced at the same implied vol", _sc_lychee_vol(1.5)),
    "iv_x1.2": ("every voucher priced at 20% higher implied vol", _sc_iv(1.2)),
    "iv_x0.8": ("every voucher priced at 20% lower implied vol", _sc_iv(0.8)),
    # reshuffled time
    "bootstrap_1": ("non-option products: 2,500-tick blocks reordered (seed 1)", _sc_bootstrap(1)),
    "bootstrap_2": ("same, seed 2", _sc_bootstrap(2)),
    "bootstrap_3": ("same, seed 3", _sc_bootstrap(3)),
}


def apply(name: str, prices: pd.DataFrame, trades: pd.DataFrame, day: int):
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario {name!r}; options: {sorted(SCENARIOS)}")
    p, t = prices.copy(), trades.copy()
    p, t = SCENARIOS[name][1](p, t, day)
    return p, t


if __name__ == "__main__":
    for k, (desc, _) in SCENARIOS.items():
        print(f"{k:24s} {desc}")
