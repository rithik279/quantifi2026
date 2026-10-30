"""Shared helpers for the adaptive-variant experiments (02_ and 03_ scripts)."""

import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "src", "strategies"))
import backtester as bt  # noqa: E402
import options  # noqa: E402
import pearls  # noqa: E402
import scenarios as sc  # noqa: E402
import standalone  # noqa: E402

OUT = os.path.join(ROOT, "outputs", "adaptive")


def trader_and_products(unit, overrides):
    if unit == "TOFFEE_CAKE":
        prm = dict(standalone.PARAMS[unit], **overrides)
        return (lambda: standalone.Trader({unit: prm})), [unit]
    if unit == "PINK_PEARLS":
        prm = dict(pearls.PARAMS[unit], **overrides)
        return (lambda: pearls.Trader({unit: prm})), pearls.PEARLS
    return (lambda: options.Trader(overrides)), sc.OPTION_PRODUCTS


def evaluate(job):
    """job = (unit, variant name, parameter overrides, scenario) -> 3-day total and worst day."""
    unit, variant, overrides, scenario = job
    factory, products = trader_and_products(unit, overrides)
    res = bt.backtest(factory, products=products, record_every=0, scenario=scenario)
    if unit == "OPTIONS_BOOK":
        pnl = {d.day: d.total for d in res.days}
    else:
        pnl = {d.day: d.pnl_by_product.get(unit, 0.0) for d in res.days}
    return dict(unit=unit, variant=variant, scenario=scenario, total=sum(pnl.values()), worst_day=min(pnl.values()))
