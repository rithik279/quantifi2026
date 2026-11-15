"""Shared harness for robustness tests: how to build and score each strategy "unit".

A unit is one thing we tune: a single standalone product, a single pearl, the basket group, or the
whole options book. `evaluate(unit, overrides, stress)` runs days -2, -1, 0 with the chosen
parameters plus `overrides`, and returns the unit's PnL per day.
"""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import basket  # noqa: E402
import options  # noqa: E402
import pearls  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "robustness")
os.makedirs(OUT, exist_ok=True)
DAYS = (-2, -1, 0)

UNITS = {}
for p in standalone.PARAMS:
    UNITS[p] = dict(group="standalone", base=standalone.PARAMS[p], products=[p])
for p in pearls.PARAMS:
    UNITS[p] = dict(group="pearls", base=pearls.PARAMS[p], products=pearls.PEARLS)
UNITS["BASKET_GROUP"] = dict(group="basket", base=basket.PARAMS, products=[basket.BASKET] + list(basket.WEIGHTS))
UNITS["OPTIONS_BOOK"] = dict(group="options", base=options.PARAMS, products=[options.UNDERLYING] + list(options.VOUCHERS))


class _NoDay(options.Trader):
    """Options trader that ignores the backtester's day hook: always assumes scoring day 1."""

    def set_day(self, day):
        pass


def make_trader(unit, prm, no_day=False):
    g = UNITS[unit]["group"]
    if g == "standalone":
        return standalone.Trader({unit: prm})
    if g == "pearls":
        return pearls.Trader({unit: prm})
    if g == "basket":
        return basket.Trader(prm)
    return (_NoDay if no_day else options.Trader)(prm)


def evaluate(job):
    """job = (unit, overrides: dict, stress: dict, tag: str)"""
    unit, overrides, stress, tag = job
    u = UNITS[unit]
    prm = dict(u["base"], **overrides)
    stress = dict(stress)
    no_day = stress.pop("no_day", False)
    res = bt.backtest(lambda: make_trader(unit, prm, no_day), DAYS, u["products"], record_every=0, **stress)
    if u["group"] in ("basket", "options"):
        pnl = {d.day: d.total for d in res.days}
    else:
        pnl = {d.day: d.pnl_by_product.get(unit, 0.0) for d in res.days}
    return dict(unit=unit, group=u["group"], tag=tag, overrides=str(overrides), stress=str(stress) + (" no_day" if no_day else ""),
                d_2=pnl[-2], d_1=pnl[-1], d0=pnl[0], total=sum(pnl.values()), min_day=min(pnl.values()))
