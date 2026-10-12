import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta, timezone
from src.observability.replay_logger import (
    ReplayLogger, ReplayEvent,
    EVENT_INVALID_BAR_SKIPPED, EVENT_FEATURE_GENERATION,
    EVENT_FEATURE_SIGNAL_CREATED, EVENT_STRATEGY_SIGNAL_CREATED,
)
from src.replay.replay_engine import run


def make_bars(n: int, base: float = 100.0, step: float = 0.5) -> list[dict]:
    # Real date arithmetic; see the identical note in test_replay_engine.py.
    _start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [{"t": (_start + timedelta(days=i)).isoformat(),
             "o": base+i*step, "h": base+i*step+0.1,
             "l": base+i*step-0.1, "c": base+i*step,
             "v": 1000.0, "symbol": "GLD"} for i in range(n)]


def test_event_ordering():
    logger = ReplayLogger()
    run(make_bars(30), logger=logger)
    events = logger.events()
    timestamps = [e.timestamp for e in events]
    assert timestamps == sorted(timestamps)


def test_metadata_preserved():
    logger = ReplayLogger()
    run(make_bars(30), logger=logger)
    fe = logger.of_type(EVENT_FEATURE_GENERATION)
    assert all("feature_key" in e.metadata and "value" in e.metadata for e in fe)


def test_invalid_bar_event():
    logger = ReplayLogger()
    bars = make_bars(30)
    bars[0] = {"t": "bad", "symbol": "GLD"}
    run(bars, logger=logger)
    skipped = logger.of_type(EVENT_INVALID_BAR_SKIPPED)
    assert len(skipped) >= 1
    assert "errors" in skipped[0].metadata


def test_stable_event_schema():
    logger = ReplayLogger()
    run(make_bars(30), logger=logger)
    for e in logger.events():
        assert isinstance(e, ReplayEvent)
        assert isinstance(e.timestamp, datetime)
        assert isinstance(e.event_type, str)
        assert isinstance(e.symbol, str)
        assert isinstance(e.stage, str)
        assert isinstance(e.metadata, dict)


def test_strategy_signal_events_match_signals():
    logger = ReplayLogger()
    signals = run(make_bars(30), logger=logger)
    assert logger.of_type(EVENT_STRATEGY_SIGNAL_CREATED).__len__() == len(signals)


def test_no_logger_still_works():
    result = run(make_bars(30), logger=None)
    assert len(result) > 0


def test_logger_passive_same_output():
    bars = make_bars(30)
    logger = ReplayLogger()
    with_log = run(bars, logger=logger)
    without_log = run(bars, logger=None)
    assert len(with_log) == len(without_log)
    for a, b in zip(with_log, without_log):
        assert a.direction == b.direction and a.confidence == b.confidence


def test_append_only():
    logger = ReplayLogger()
    run(make_bars(30), logger=logger)
    count_after_first = logger.count()
    # events() returns a copy — internal list unchanged
    _ = logger.events()
    assert logger.count() == count_after_first


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
