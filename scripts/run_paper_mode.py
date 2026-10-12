"""
scripts/run_paper_mode.py

Initializes the system in PAPER mode via RuntimeConfig + ExecutionRouter.
Verifies router selects AlpacaPaperBroker, prints account state.
No orders submitted. No loops. No architecture changes.

Usage:
    cd D:\\GLD_Trading_Platform
    python scripts/run_paper_mode.py
"""
import sys
import os

def _load_dotenv() -> None:
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.exists(env_path):
        print(f"[warn] No .env found at {env_path} — relying on shell environment.")
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_dotenv()
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from src.runtime.mode import RuntimeMode
from src.runtime.config import RuntimeConfig
from src.runtime.execution_router import ExecutionRouter
from src.brokers.alpaca_paper_broker import AlpacaPaperBroker


def _safe_float(obj, field: str, default: float = 0.0) -> float:
    val = getattr(obj, field, None)
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def main() -> None:
    # Force PAPER mode regardless of env
    config = RuntimeConfig(
        mode=RuntimeMode.PAPER,
        symbol=os.environ.get("SYMBOL", "GLD").upper(),
        strict_mode=True,
        allow_live_trading=False,
    )

    print(f"[runtime] Mode    : {config.mode.value}")
    print(f"[runtime] Symbol  : {config.symbol}")

    router = ExecutionRouter(config)
    backend = router.get_backend()

    # Verify correct backend selected
    if not isinstance(backend, AlpacaPaperBroker):
        print(f"[error] Expected AlpacaPaperBroker, got {type(backend).__name__}")
        sys.exit(1)

    print(f"[runtime] Backend : {type(backend).__name__} ✓")

    # Fetch and print account state
    try:
        from alpaca.trading.client import TradingClient
        acct = backend._client.get_account()
        print()
        print("=== Paper Account State ===")
        print(f"  Status         : {getattr(acct, 'status', 'unknown')}")
        print(f"  Buying Power   : ${_safe_float(acct, 'buying_power'):,.2f}")
        print(f"  Cash           : ${_safe_float(acct, 'cash'):,.2f}")
        print(f"  Portfolio Value: ${_safe_float(acct, 'portfolio_value'):,.2f}")
        print(f"  Unrealized P&L : ${_safe_float(acct, 'unrealized_pl'):,.2f}")
        print(f"  Realized P&L   : ${_safe_float(acct, 'realized_pl'):,.2f}")
        print("===========================")
    except Exception as e:
        print(f"[error] Failed to fetch account state: {e}")
        sys.exit(1)

    print("[runtime] PAPER mode verified. No orders submitted.")


if __name__ == "__main__":
    main()
