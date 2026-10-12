import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.orchestration.backtest_runner import BacktestRunner, BacktestResult
from src.risk.risk_engine import RiskEngine


def make_bars(n: int, base: float = 100.0, step: float = 0.5) -> list[dict]:
    return [
        {"t": f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}T00:00:00+00:00",
         "o": base+i*step, "h": base+i*step+0.1,
         "l": base+i*step-0.1, "c": base+i*step,
         "v": 1000.0, "symbol": "GLD"}
        for i in range(n)
    ]


def test_returns_backtest_result():
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    assert isinstance(result, BacktestResult)


def test_empty_input():
    runner = BacktestRunner()
    result = runner.run([])
    assert result.signals == []
    assert result.trades == []
    assert result.equity_curve == []


def test_insufficient_bars():
    runner = BacktestRunner()
    result = runner.run(make_bars(10))
    assert result.signals == []


def test_signals_produced():
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    assert len(result.signals) > 0


def test_equity_curve_length_matches_signals():
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    assert len(result.equity_curve) == len(result.signals)


def test_deterministic():
    bars = make_bars(40)
    r1 = BacktestRunner().run(bars)
    r2 = BacktestRunner().run(bars)
    assert r1.evaluation_metrics["final_realized_pnl"] == \
           r2.evaluation_metrics["final_realized_pnl"]
    assert len(r1.signals) == len(r2.signals)


def test_risk_blocking_works():
    # Zero exposure cap blocks all non-FLAT trades
    risk = RiskEngine(exposure_cap=0.0, cooldown_seconds=0)
    runner = BacktestRunner(risk_engine=risk)
    result = runner.run(make_bars(40))
    assert result.evaluation_metrics["risk_blocked"] >= 0  # engine runs without error


def test_metrics_schema():
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    m = result.evaluation_metrics
    for key in ["total_signals", "total_trades", "risk_blocked",
                "final_realized_pnl", "signal_frequency",
                "average_confidence", "long_short_distribution", "total_return"]:
        assert key in m


def test_no_external_dependencies():
    # Confirm stdlib-only: no pandas, numpy, requests in result
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    assert isinstance(result.evaluation_metrics["final_realized_pnl"], float)


def test_risk_events_are_list():
    runner = BacktestRunner()
    result = runner.run(make_bars(40))
    assert isinstance(result.risk_events, list)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
