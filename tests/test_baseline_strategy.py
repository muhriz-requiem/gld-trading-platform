import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.signals.signal_schema import FeatureSignal
from src.contracts.signal import Signal, SignalDirection
from src.strategies.baseline_momentum import generate, LONG_THRESHOLD, SHORT_THRESHOLD


def make_fs(value: float) -> list[FeatureSignal]:
    return [FeatureSignal(
        timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        symbol="GLD",
        signal_name="signal_momentum_v1",
        value=value,
        confidence=0.5,
    )]


def test_long_signal():
    result = generate(make_fs(LONG_THRESHOLD + 0.01))
    assert result.direction == SignalDirection.LONG

def test_short_signal():
    result = generate(make_fs(SHORT_THRESHOLD - 0.01))
    assert result.direction == SignalDirection.SHORT

def test_flat_signal():
    result = generate(make_fs(0.0))
    assert result.direction == SignalDirection.FLAT
    assert result.confidence == 0.0

def test_output_type():
    result = generate(make_fs(0.05))
    assert isinstance(result, Signal)

def test_no_nan():
    result = generate(make_fs(0.05))
    assert not math.isnan(result.confidence)

def test_deterministic():
    fs = make_fs(0.05)
    assert generate(fs) == generate(fs)

def test_stable_strategy_id():
    result = generate(make_fs(0.05))
    assert result.strategy_id == "baseline_momentum_v1"

def test_missing_signal_raises():
    try:
        generate([])
        assert False, "should raise"
    except ValueError:
        pass

def test_symbol_preserved():
    result = generate(make_fs(0.05))
    assert result.symbol == "GLD"

def test_confidence_in_range():
    for v in [0.05, 0.10, 0.20, -0.05, -0.10]:
        r = generate(make_fs(v))
        assert 0.0 <= r.confidence <= 1.0


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
