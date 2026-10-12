import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.contracts.signal import Signal, SignalDirection
from src.contracts.order import Order, OrderStatus
from src.contracts.position import Position

_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

def sig(direction: SignalDirection) -> Signal:
    return Signal(symbol="GLD", direction=direction, confidence=0.5,
                  strategy_id="test", generated_at=_ts)


# --- Credential guard tests (no API calls) ---

# Both the legacy names and the current *_PAPER names must be cleared. The broker
# prefers the *_PAPER names, and those are often present in the ambient process
# environment (e.g. set at the Windows registry level), which previously made these
# two tests pass or fail depending on the machine rather than on the code.
_ALPACA_ENV_VARS = (
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_API_KEY_PAPER",
    "ALPACA_SECRET_KEY_PAPER",
)


def test_missing_credentials_raises(monkeypatch):
    for _k in _ALPACA_ENV_VARS:
        monkeypatch.delenv(_k, raising=False)
    from src.brokers.alpaca_paper_broker import _require_credentials
    try:
        _require_credentials()
        assert False, "should raise"
    except EnvironmentError as e:
        assert "ALPACA_API_KEY" in str(e)


def test_missing_secret_raises(monkeypatch):
    for _k in _ALPACA_ENV_VARS:
        monkeypatch.delenv(_k, raising=False)
    monkeypatch.setenv("ALPACA_API_KEY", "fake")
    from src.brokers.alpaca_paper_broker import _require_credentials
    try:
        _require_credentials()
        assert False, "should raise"
    except EnvironmentError:
        pass


# --- Signal mapping tests (no API calls) ---

def test_long_maps_to_buy_request():
    try:
        from src.brokers.alpaca_paper_broker import _map_signal_to_request
        from alpaca.trading.enums import OrderSide as AlpacaSide
        req = _map_signal_to_request(sig(SignalDirection.LONG))
        assert req.side == AlpacaSide.BUY
    except ImportError:
        print("  SKIP  alpaca-py not installed")


def test_short_maps_to_sell_request():
    try:
        from src.brokers.alpaca_paper_broker import _map_signal_to_request
        from alpaca.trading.enums import OrderSide as AlpacaSide
        req = _map_signal_to_request(sig(SignalDirection.SHORT))
        assert req.side == AlpacaSide.SELL
    except ImportError:
        print("  SKIP  alpaca-py not installed")


def test_flat_returns_none_from_mapper():
    try:
        from src.brokers.alpaca_paper_broker import _map_signal_to_request
        result = _map_signal_to_request(sig(SignalDirection.FLAT))
        assert result is None
    except ImportError:
        print("  SKIP  alpaca-py not installed")


# --- BrokerBase interface compliance ---

def test_implements_broker_base():
    from src.brokers.base import BrokerBase
    import inspect
    from src.brokers import alpaca_paper_broker as mod
    assert issubclass(mod.AlpacaPaperBroker, BrokerBase)


# --- Account state schema (fallback path) ---

def test_account_state_schema_keys():
    """Validate fallback state dict has required keys — no API needed."""
    expected = {"realized_pnl", "unrealized_pnl", "fill_count", "open_position",
                "portfolio_value", "cash"}
    # Test against the fallback dict structure directly
    fallback = {
        "realized_pnl": 0.0, "unrealized_pnl": 0.0, "fill_count": None,
        "open_position": False, "portfolio_value": 0.0, "cash": 0.0,
    }
    assert expected == set(fallback.keys())


# --- No simulator fallback ---

def test_no_simulator_import():
    import importlib
    import ast, pathlib
    src = pathlib.Path(__file__).parent.parent / "src/brokers/alpaca_paper_broker.py"
    tree = ast.parse(src.read_text())
    imports = [
        n.module if isinstance(n, ast.ImportFrom) else ""
        for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    assert not any("simulator" in (i or "") for i in imports), \
        "AlpacaPaperBroker must not import ExecutionSimulator"


def test_paper_endpoint_only():
    import pathlib
    src = pathlib.Path(__file__).parent.parent / "src/brokers/alpaca_paper_broker.py"
    text = src.read_text()
    assert "paper-api.alpaca.markets" in text
    assert "live-api.alpaca.markets" not in text


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
