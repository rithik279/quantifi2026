"""Shared loaders for the organizer CSVs (semicolon-separated)."""

import os
from typing import Iterable

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data", "raw")
DAYS = (-2, -1, 0)
TICKS_PER_DAY = 10_000


def prices(days: Iterable[int] = DAYS) -> pd.DataFrame:
    """Long-format order book snapshots with a global tick index `t` (day * 10_000 + timestamp / 100)."""
    df = pd.concat([pd.read_csv(os.path.join(DATA_DIR, f"prices_day_{d}.csv"), sep=";") for d in days])
    df["t"] = (df["day"] - min(days)) * TICKS_PER_DAY + df["timestamp"] // 100
    df["spread"] = df["ask_price_1"] - df["bid_price_1"]
    return df.reset_index(drop=True)


def trades(days: Iterable[int] = DAYS) -> pd.DataFrame:
    df = pd.concat([pd.read_csv(os.path.join(DATA_DIR, f"trades_day_{d}.csv"), sep=";").assign(day=d) for d in days])
    df["t"] = (df["day"] - min(days)) * TICKS_PER_DAY + df["timestamp"] // 100
    return df.reset_index(drop=True)


def wide(df: pd.DataFrame, col: str = "mid_price", products: Iterable[str] = None) -> pd.DataFrame:
    """Pivot a prices frame to one column per product, indexed by global tick `t`."""
    if products is not None:
        df = df[df["product"].isin(list(products))]
    return df.pivot(index="t", columns="product", values=col)
