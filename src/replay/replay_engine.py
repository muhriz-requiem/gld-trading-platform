from src.contracts.signal import Signal
from src.contracts.validation.bar_validator import validate_bar
from src.signals.signal_schema import FeatureSignal
from src.signals.signal_registry import SIGNAL_REGISTRY
from src.strategies.baseline_momentum import generate as momentum_strategy
from src.data.time_utils import parse_alpaca_timestamp
from src.observability.replay_logger import (
    ReplayLogger,
    EVENT_INVALID_BAR_SKIPPED,
    EVENT_FEATURE_GENERATION,
    EVENT_FEATURE_SIGNAL_CREATED,
    EVENT_STRATEGY_SIGNAL_CREATED,
)

_MIN_WINDOW = 21


def run(bars: list[dict], logger: ReplayLogger | None = None) -> list[Signal]:
    """
    Deterministic sequential replay over a historical bar list.
    Logger is optional and passive — it never alters signal or feature logic.
    """
    signals: list[Signal] = []
    window: list[dict] = []

    for bar in bars:
        valid, errors = validate_bar(bar)
        if not valid:
            if logger:
                logger.log(EVENT_INVALID_BAR_SKIPPED, symbol=bar.get("symbol", ""),
                           stage="replay", metadata={"errors": errors})
            continue

        window.append(bar)

        if len(window) < _MIN_WINDOW:
            continue

        ts = parse_alpaca_timestamp(bar["t"])
        symbol = bar["symbol"]
        feature_signals: list[FeatureSignal] = []

        for signal_name, entry in SIGNAL_REGISTRY.items():
            try:
                feature_map = entry["feature_fn"](window, **entry["params"])
                value = feature_map[entry["feature_key"]]

                if logger:
                    logger.log(EVENT_FEATURE_GENERATION, symbol=symbol,
                               stage="feature", metadata={"feature_key": entry["feature_key"],
                                                          "value": value}, timestamp=ts)

                fs = FeatureSignal(timestamp=ts, symbol=symbol,
                                   signal_name=signal_name, value=value, confidence=0.5)
                feature_signals.append(fs)

                if logger:
                    logger.log(EVENT_FEATURE_SIGNAL_CREATED, symbol=symbol,
                               stage="signal", metadata={"signal_name": signal_name,
                                                         "value": value}, timestamp=ts)
            except ValueError:
                continue

        if not feature_signals:
            continue

        try:
            signal = momentum_strategy(feature_signals)
            signals.append(signal)

            if logger:
                logger.log(EVENT_STRATEGY_SIGNAL_CREATED, symbol=symbol,
                           stage="strategy", metadata={"direction": signal.direction,
                                                       "confidence": signal.confidence},
                           timestamp=ts)
        except ValueError:
            continue

    return signals
