from dataclasses import dataclass
from datetime import datetime


@dataclass
class FeatureSignal:
    """
    Intermediate signal derived from feature values.
    Produced by the signal layer — NOT by strategies.
    Strategies (Stage 5) consume FeatureSignals and emit src.contracts.signal.Signal.

    Fields:
        timestamp:   UTC-aware datetime aligned to the source bar
        symbol:      Ticker (e.g. "GLD")
        signal_name: Stable name matching SIGNAL_REGISTRY key
        value:       Raw numeric signal value (derived from features)
        confidence:  Normalised confidence score in range [0.0, 1.0]
    """
    timestamp: datetime
    symbol: str
    signal_name: str
    value: float
    confidence: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be UTC-aware")
        import math
        if math.isnan(self.value) or math.isnan(self.confidence):
            raise ValueError("value and confidence must not be NaN")
