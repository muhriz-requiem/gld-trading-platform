from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class SignalDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Signal:
    symbol: str
    direction: SignalDirection
    confidence: float          # 0.0 - 1.0
    strategy_id: str
    generated_at: datetime
    metadata: dict | None = None
