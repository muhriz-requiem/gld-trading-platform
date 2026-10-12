from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    notional: float | None = None      # dollar-based execution; overrides qty when set
    status: OrderStatus = OrderStatus.PENDING
    order_id: str | None = None
    created_at: datetime | None = None
    filled_at: datetime | None = None
    filled_price: float | None = None

    def __post_init__(self) -> None:
        if self.notional is not None and self.quantity != 0:
            raise ValueError(
                "Only one of (quantity, notional) may be set. "
                "Set quantity=0 when using notional."
            )
