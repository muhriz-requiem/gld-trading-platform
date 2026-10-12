import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.features.kernel import log_return, rolling_volatility, momentum

# --- Synthetic bar factory ---
def make_bars(closes: list[float]) -> list[dict]:
    return [
        {"t": f"2024-01-{i+1:02d}T00:00:00+00:00", "o": c, "h": c, "l": c, "c": c, "v": 1000.0, "symbol": "GLD"}
        for i, c in enumerate(closes)
    ]


def test_log_return_type_and_key():
    bars = make_bars([100.0, 102.0])
    result = log_return(bars)
    assert isinstance(result, dict)
    assert "log_return_v1" in result
    assert isinstance(result["log_return_v1"], float)


def test_log_return_no_nan():
    bars = make_bars([100.0, 102.0])
    result = log_return(bars)
    assert not math.isnan(result["log_return_v1"])


def test_log_return_deterministic():
    bars = make_bars([100.0, 105.0])
    assert log_return(bars) == log_return(bars)


def test_log_return_insufficient_bars():
    try:
        log_return(make_bars([100.0]))
        assert False, "should raise"
    except ValueError:
        pass


def test_rolling_volatility_type_and_key():
    bars = make_bars([100.0 + i for i in range(22)])
    result = rolling_volatility(bars, window=20)
    assert "rolling_volatility_v1" in result
    assert isinstance(result["rolling_volatility_v1"], float)


def test_rolling_volatility_no_nan():
    bars = make_bars([100.0 + i * 0.5 for i in range(22)])
    result = rolling_volatility(bars, window=20)
    assert not math.isnan(result["rolling_volatility_v1"])


def test_rolling_volatility_deterministic():
    bars = make_bars([100.0 + i for i in range(22)])
    assert rolling_volatility(bars, window=20) == rolling_volatility(bars, window=20)


def test_momentum_type_and_key():
    bars = make_bars([100.0 + i for i in range(22)])
    result = momentum(bars, window=20)
    assert "momentum_v1" in result
    assert isinstance(result["momentum_v1"], float)


def test_momentum_no_nan():
    bars = make_bars([100.0 + i for i in range(22)])
    result = momentum(bars, window=20)
    assert not math.isnan(result["momentum_v1"])


def test_momentum_deterministic():
    bars = make_bars([100.0 + i for i in range(22)])
    assert momentum(bars, window=20) == momentum(bars, window=20)


def test_momentum_insufficient_bars():
    try:
        momentum(make_bars([100.0] * 5), window=20)
        assert False, "should raise"
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
