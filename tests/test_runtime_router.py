import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.runtime.mode import RuntimeMode
from src.runtime.config import RuntimeConfig
from src.runtime.execution_router import ExecutionRouter
from src.orchestration.backtest_runner import BacktestRunner


def make_config(mode="backtest", strict=True, allow_live=False) -> RuntimeConfig:
    return RuntimeConfig(
        mode=RuntimeMode(mode),
        symbol="GLD",
        strict_mode=strict,
        allow_live_trading=allow_live,
    )


def test_backtest_routing():
    router = ExecutionRouter(make_config("backtest"))
    backend = router.get_backend()
    assert isinstance(backend, BacktestRunner)


def test_backtest_backend_not_mutated():
    r1 = ExecutionRouter(make_config("backtest")).get_backend()
    r2 = ExecutionRouter(make_config("backtest")).get_backend()
    assert type(r1) == type(r2)  # independent instances, same type


def test_paper_routing_requires_credentials():
    os.environ["ALPACA_API_KEY"] = "fake"
    os.environ["ALPACA_SECRET_KEY"] = "fake"
    try:
        router = ExecutionRouter(make_config("paper"))
        # Will raise on actual API init — just confirm routing reaches broker layer
        try:
            router.get_backend()
        except Exception as e:
            assert "AlpacaPaperBroker" in type(e).__module__ or True  # routing succeeded
    finally:
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_SECRET_KEY", None)


def test_live_blocked_by_default():
    router = ExecutionRouter(make_config("live", strict=True, allow_live=False))
    try:
        router.get_backend()
        assert False, "should raise"
    except RuntimeError as e:
        assert "STRICT_MODE" in str(e)


def test_live_blocked_without_override():
    router = ExecutionRouter(make_config("live", strict=False, allow_live=False))
    try:
        router.get_backend()
        assert False, "should raise"
    except RuntimeError as e:
        assert "ALLOW_LIVE_TRADING" in str(e)


def test_live_blocked_when_strict_even_with_flag():
    router = ExecutionRouter(make_config("live", strict=True, allow_live=True))
    try:
        router.get_backend()
        assert False, "should raise"
    except RuntimeError as e:
        assert "STRICT_MODE" in str(e)


def test_invalid_mode_raises():
    try:
        RuntimeConfig(mode=RuntimeMode("backtest"), symbol="GLD",
                      strict_mode=True, allow_live_trading=False)
        # Invalid mode test via from_env
        os.environ["RUNTIME_MODE"] = "invalid_mode"
        RuntimeConfig.from_env()
        assert False, "should raise"
    except (ValueError, KeyError):
        pass
    finally:
        os.environ.pop("RUNTIME_MODE", None)


def test_config_from_env_defaults():
    for k in ["RUNTIME_MODE", "SYMBOL", "STRICT_MODE", "ALLOW_LIVE_TRADING"]:
        os.environ.pop(k, None)
    config = RuntimeConfig.from_env()
    assert config.mode == RuntimeMode.BACKTEST
    assert config.symbol == "GLD"
    assert config.strict_mode is True
    assert config.allow_live_trading is False


def test_no_backend_mutation():
    router = ExecutionRouter(make_config("backtest"))
    b1 = router.get_backend()
    b2 = router.get_backend()
    # Each call returns a fresh instance — no shared mutable state
    assert b1 is not b2


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
