from src.signals.signal_schema import FeatureSignal
from src.contracts.signal import Signal, SignalDirection
from datetime import timezone

STRATEGY_ID = "baseline_momentum_v1"
SIGNAL_NAME = "signal_momentum_v1"
LONG_THRESHOLD = 0.02   # momentum_v1 > +2% → LONG
SHORT_THRESHOLD = -0.02  # momentum_v1 < -2% → SHORT


def generate(feature_signals: list[FeatureSignal]) -> Signal:
    """
    Consume momentum_v1 FeatureSignal and emit a single StrategySignal.
    Stateless. Deterministic. No execution or sizing logic.

    Raises:
        ValueError: if no momentum_v1 signal found in input list.
    """
    momentum_signal = next(
        (fs for fs in feature_signals if fs.signal_name == SIGNAL_NAME), None
    )
    if momentum_signal is None:
        raise ValueError(f"Required signal '{SIGNAL_NAME}' not found in input")

    value = momentum_signal.value

    if value > LONG_THRESHOLD:
        direction = SignalDirection.LONG
        confidence = min(value / (LONG_THRESHOLD * 5), 1.0)
    elif value < SHORT_THRESHOLD:
        direction = SignalDirection.SHORT
        confidence = min(abs(value) / (abs(SHORT_THRESHOLD) * 5), 1.0)
    else:
        direction = SignalDirection.FLAT
        confidence = 0.0

    return Signal(
        symbol=momentum_signal.symbol,
        direction=direction,
        confidence=round(confidence, 6),
        strategy_id=STRATEGY_ID,
        generated_at=momentum_signal.timestamp,
        metadata={"momentum_v1": value},
    )
