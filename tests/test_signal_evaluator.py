import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.contracts.signal import Signal, SignalDirection
from src.evaluation.signal_evaluator import (
    directional_accuracy, signal_frequency, average_confidence, long_short_distribution
)

_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

def make_signal(direction: SignalDirection, confidence: float = 0.5) -> Signal:
    return Signal(symbol="GLD", direction=direction, confidence=confidence,
                  strategy_id="test", generated_at=_ts)


# --- directional_accuracy ---

def test_accuracy_all_correct():
    signals = [make_signal(SignalDirection.LONG), make_signal(SignalDirection.SHORT)]
    assert directional_accuracy(signals, [0.01, -0.01]) == 1.0

def test_accuracy_all_wrong():
    signals = [make_signal(SignalDirection.LONG), make_signal(SignalDirection.SHORT)]
    assert directional_accuracy(signals, [-0.01, 0.01]) == 0.0

def test_accuracy_flat_ignored():
    signals = [make_signal(SignalDirection.FLAT), make_signal(SignalDirection.LONG)]
    assert directional_accuracy(signals, [-0.99, 0.01]) == 1.0

def test_accuracy_all_flat():
    signals = [make_signal(SignalDirection.FLAT)]
    assert directional_accuracy(signals, [0.01]) == 0.0

def test_accuracy_length_mismatch():
    try:
        directional_accuracy([make_signal(SignalDirection.LONG)], [0.01, 0.02])
        assert False
    except ValueError:
        pass

def test_accuracy_deterministic():
    signals = [make_signal(SignalDirection.LONG)]
    assert directional_accuracy(signals, [0.01]) == directional_accuracy(signals, [0.01])


# --- signal_frequency ---

def test_frequency_sums_to_one():
    signals = [make_signal(SignalDirection.LONG), make_signal(SignalDirection.SHORT),
               make_signal(SignalDirection.FLAT)]
    freq = signal_frequency(signals)
    assert abs(sum(freq.values()) - 1.0) < 1e-9

def test_frequency_empty():
    freq = signal_frequency([])
    assert freq == {"long": 0.0, "short": 0.0, "flat": 0.0}


# --- average_confidence ---

def test_avg_confidence_correct():
    signals = [make_signal(SignalDirection.LONG, 0.4), make_signal(SignalDirection.LONG, 0.6)]
    assert abs(average_confidence(signals) - 0.5) < 1e-9

def test_avg_confidence_empty():
    assert average_confidence([]) == 0.0

def test_avg_confidence_no_nan():
    signals = [make_signal(SignalDirection.LONG, 0.7)]
    assert not math.isnan(average_confidence(signals))


# --- long_short_distribution ---

def test_distribution_counts():
    signals = [make_signal(SignalDirection.LONG)] * 3 + [make_signal(SignalDirection.SHORT)] * 2
    dist = long_short_distribution(signals)
    assert dist == {"long": 3, "short": 2, "flat": 0}

def test_distribution_empty():
    assert long_short_distribution([]) == {"long": 0, "short": 0, "flat": 0}


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
