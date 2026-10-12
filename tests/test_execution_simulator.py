import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.contracts.signal import Signal, SignalDirection
from src.execution.simulator import ExecutionSimulator, FillRecord

_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

def sig(direction: SignalDirection) -> Signal:
    return Signal(symbol="GLD", direction=direction, confidence=0.5,
                  strategy_id="test", generated_at=_ts)


def test_long_entry():
    sim = ExecutionSimulator()
    fill = sim.process(sig(SignalDirection.LONG), 180.0)
    assert fill is not None
    assert fill.direction == SignalDirection.LONG
    assert fill.fill_price == 180.0


def test_short_entry():
    sim = ExecutionSimulator()
    fill = sim.process(sig(SignalDirection.SHORT), 175.0)
    assert fill is not None
    assert fill.direction == SignalDirection.SHORT


def test_flat_closes_long():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.LONG), 180.0)
    fill = sim.process(sig(SignalDirection.FLAT), 185.0)
    assert fill is not None
    assert fill.realized_pnl == 5.0
    assert sim.state().position is None


def test_flat_closes_short():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.SHORT), 180.0)
    fill = sim.process(sig(SignalDirection.FLAT), 175.0)
    assert fill.realized_pnl == 5.0


def test_repeated_long_is_noop():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.LONG), 180.0)
    fill = sim.process(sig(SignalDirection.LONG), 182.0)
    assert fill is None


def test_repeated_short_is_noop():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.SHORT), 180.0)
    fill = sim.process(sig(SignalDirection.SHORT), 178.0)
    assert fill is None


def test_flat_when_flat_is_noop():
    sim = ExecutionSimulator()
    fill = sim.process(sig(SignalDirection.FLAT), 180.0)
    assert fill is None


def test_realized_pnl_long():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.LONG), 100.0)
    sim.process(sig(SignalDirection.FLAT), 110.0)
    assert abs(sim.state().realized_pnl - 10.0) < 1e-9


def test_realized_pnl_short():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.SHORT), 100.0)
    sim.process(sig(SignalDirection.FLAT), 90.0)
    assert abs(sim.state().realized_pnl - 10.0) < 1e-9


def test_unrealized_pnl():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.LONG), 100.0)
    sim.update_price(105.0)
    assert abs(sim.unrealized_pnl - 5.0) < 1e-9


def test_deterministic_replay():
    def run_sim():
        sim = ExecutionSimulator()
        sim.process(sig(SignalDirection.LONG), 100.0)
        sim.update_price(105.0)
        sim.process(sig(SignalDirection.FLAT), 105.0)
        return sim.state().realized_pnl
    assert run_sim() == run_sim()


def test_fill_history_ordered():
    sim = ExecutionSimulator()
    sim.process(sig(SignalDirection.LONG), 100.0)
    sim.process(sig(SignalDirection.FLAT), 110.0)
    fills = sim.state().fills
    assert len(fills) == 2
    assert all(isinstance(f, FillRecord) for f in fills)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
