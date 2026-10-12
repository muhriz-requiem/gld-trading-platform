import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from src.replay.replay_engine import run
from src.contracts.signal import Signal, SignalDirection


def make_bars(n: int, base: float = 100.0, step: float = 0.5) -> list[dict]:
    # Real date arithmetic, not f"2024-01-{(i % 28) + 1}": that form wraps at i=28 and
    # produced a non-monotonic bar series for n>28, so the engine faithfully emitted
    # signals stamped out of order.
    _start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "t": (_start + timedelta(days=i)).isoformat(),
            "o": base + i * step,
            "h": base + i * step + 0.1,
            "l": base + i * step - 0.1,
            "c": base + i * step,
            "v": 1000.0,
            "symbol": "GLD",
        }
        for i in range(n)
    ]


def test_empty_input():
    assert run([]) == []


def test_insufficient_bars_returns_empty():
    # Fewer than minimum window — no signals
    assert run(make_bars(10)) == []


def test_sufficient_bars_produces_signals():
    result = run(make_bars(30))
    assert len(result) > 0


def test_output_type():
    result = run(make_bars(30))
    assert all(isinstance(s, Signal) for s in result)


def test_deterministic():
    bars = make_bars(30)
    assert run(bars) == run(bars)


def test_signal_ordering():
    result = run(make_bars(30))
    timestamps = [s.generated_at for s in result]
    assert timestamps == sorted(timestamps)


def test_invalid_bar_skipped():
    bars = make_bars(30)
    bars[5] = {"t": "bad", "symbol": "GLD"}  # invalid bar
    result = run(bars)
    assert isinstance(result, list)


def test_strategy_id_stable():
    result = run(make_bars(30))
    assert all(s.strategy_id == "baseline_momentum_v1" for s in result)


def test_no_portfolio_state():
    # Replay output contains only Signals — no cash, position, or PnL fields
    result = run(make_bars(30))
    for s in result:
        assert not hasattr(s, "cash")
        assert not hasattr(s, "position")
        assert not hasattr(s, "pnl")


def test_confidence_in_range():
    result = run(make_bars(30))
    assert all(0.0 <= s.confidence <= 1.0 for s in result)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
