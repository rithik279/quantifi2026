"""
Specifications: Buy order quantities are positive; sells are negative.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


Time = int
Symbol = str
Product = str
Position = int
UserId = str
ObservationValue = int


@dataclass
class Listing:
    symbol: Symbol
    product: Product
    denomination: str


@dataclass
class ConversionObservation:
    bidPrice: float
    askPrice: float
    transportFees: float
    exportTariff: float
    importTariff: float
    sugarPrice: float
    sunlightIndex: float


@dataclass
class Observation:
    plainValueObservations: Dict[Product, ObservationValue]
    conversionObservations: Dict[Product, ConversionObservation]


@dataclass
class Order:
    symbol: Symbol
    price: int
    quantity: int

    def __repr__(self) -> str:
        return f"({self.symbol}, {self.price}, {self.quantity})"


@dataclass
class OrderDepth:
    buy_orders: Dict[int, int] = field(default_factory=dict)
    sell_orders: Dict[int, int] = field(default_factory=dict)


@dataclass
class Trade:
    symbol: Symbol
    price: int
    quantity: int
    buyer: Optional[UserId] = None
    seller: Optional[UserId] = None
    timestamp: Time = 0


@dataclass
class TradingState:
    traderData: str
    timestamp: Time
    listings: Dict[Symbol, Listing]
    order_depths: Dict[Symbol, OrderDepth]
    own_trades: Dict[Symbol, List[Trade]]
    market_trades: Dict[Symbol, List[Trade]]
    position: Dict[Product, Position]
    observations: Observation

    def toJSON(self) -> str:
        return json.dumps(self, cls=ProsperityEncoder, sort_keys=True)


class ProsperityEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)
