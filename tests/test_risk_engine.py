import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone, timedelta
from src.contracts.signal import Signal, SignalDirection
from src.contracts.position import Position
from src.execution.simulator import SimulatorState, FillRecord
from src.risk.risk_engine import RiskEngine, RiskDecision

_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

def sig(direction: SignalDirection, ts=None) -> Signal:
    return Signal(symbol="GLD", direction=direction, confidence=0.5,
                  strategy_id="test", generated_at=ts or _ts)

def empty_state() -> SimulatorState:
    return SimulatorState(position=None, realized_pnl=0.0, fills=[])

def state_with_pnl(pnl: float) -> SimulatorState:
    return SimulatorState(position=None, realized_pnl=pnl, fills=[])

def fill(pnl: float) -> FillRecord:
    return FillRecord("GLD", SignalDirection.FLAT, 100.0, _ts, pnl)

def state_with_fills(pnls: list[float]) -> SimulatorState:
    return SimulatorState(position=None, realized_pnl=sum(pnls),
                          fills=[fill(p) for p in pnls])

def open_state(qty: float) -> SimulatorState:
    pos = Position("GLD", qty, 100.0, 100.0)
    return SimulatorState(position=pos, realized_pnl=0.0, fills=[])


def test_allowed_signal():
    engine = RiskEngine(cooldown_seconds=0)
    result = engine.evaluate(sig(SignalDirection.LONG), empty_state())
    assert result.allowed
    assert result.adjusted_size is not None


def test_flat_always_allowed():
    engine = RiskEngine()
    result = engine.evaluate(sig(SignalDirection.FLAT), state_with_pnl(-9999.0))
    assert result.allowed


def test_exposure_cap_blocks():
    engine = RiskEngine(exposure_cap=1.0, cooldown_seconds=0)
    result = engine.evaluate(sig(SignalDirection.LONG), open_state(1.0))
    assert not result.allowed
    assert "exposure_cap" in result.reason


def test_daily_loss_blocks():
    engine = RiskEngine(max_daily_loss=-100.0, cooldown_seconds=0)
    result = engine.evaluate(sig(SignalDirection.LONG), state_with_pnl(-200.0))
    assert not result.allowed
    assert "daily_loss" in result.reason


def test_drawdown_blocks():
    engine = RiskEngine(max_drawdown=-50.0, cooldown_seconds=0)
    # Simulate peak of 100, now at 40 → drawdown = -60
    e = RiskEngine(max_drawdown=-50.0, cooldown_seconds=0)
    e.evaluate(sig(SignalDirection.LONG), state_with_pnl(100.0))  # set peak
    result = e.evaluate(sig(SignalDirection.LONG), state_with_pnl(40.0))
    assert not result.allowed
    assert "drawdown" in result.reason


def test_consecutive_losses_blocks():
    engine = RiskEngine(max_consecutive_losses=3, cooldown_seconds=0)
    state = state_with_fills([-10.0, -10.0, -10.0])
    result = engine.evaluate(sig(SignalDirection.LONG), state)
    assert not result.allowed
    assert "consecutive" in result.reason


def test_cooldown_blocks():
    engine = RiskEngine(cooldown_seconds=300)
    engine.evaluate(sig(SignalDirection.LONG, _ts), empty_state())
    ts2 = _ts + timedelta(seconds=60)
    result = engine.evaluate(sig(SignalDirection.LONG, ts2), empty_state())
    assert not result.allowed
    assert "cooldown" in result.reason


def test_cooldown_passes_after_window():
    engine = RiskEngine(cooldown_seconds=60)
    engine.evaluate(sig(SignalDirection.LONG, _ts), empty_state())
    ts2 = _ts + timedelta(seconds=120)
    result = engine.evaluate(sig(SignalDirection.LONG, ts2), empty_state())
    assert result.allowed


def test_deterministic():
    engine1 = RiskEngine(cooldown_seconds=0)
    engine2 = RiskEngine(cooldown_seconds=0)
    s = state_with_pnl(-50.0)
    r1 = engine1.evaluate(sig(SignalDirection.LONG), s)
    r2 = engine2.evaluate(sig(SignalDirection.LONG), s)
    assert r1.allowed == r2.allowed and r1.reason == r2.reason


def test_risk_decision_type():
    engine = RiskEngine(cooldown_seconds=0)
    result = engine.evaluate(sig(SignalDirection.LONG), empty_state())
    assert isinstance(result, RiskDecision)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
