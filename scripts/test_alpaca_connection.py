"""
scripts/test_alpaca_connection.py

Smoke test for Alpaca paper account connectivity.
Loads credentials from .env, fetches account state, prints summary.
No orders. No strategy logic. No architecture changes.

Usage:
    cd D:\\GLD_Trading_Platform
    python scripts/test_alpaca_connection.py
"""
import sys
import os

# Load .env from project root
def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.normpath(env_path)
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


def _safe_float(acct, field: str, default: float = 0.0) -> float:
    """Read optional account field safely, return default if missing or None."""
    val = getattr(acct, field, None)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def main() -> None:
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        print("[error] ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env or environment.")
        sys.exit(1)

    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        print("[error] alpaca-py not installed. Run: pip install alpaca-py")
        sys.exit(1)

    print("[alpaca] Connecting to paper endpoint...")
    client = TradingClient(key, secret, paper=True)

    try:
        acct = client.get_account()
    except Exception as e:
        print(f"[error] Failed to fetch account: {e}")
        sys.exit(1)

    status = getattr(acct, "status", "unknown")

    print()
    print("=== Alpaca Paper Account ===")
    print(f"  Status         : {status}")
    print(f"  Buying Power   : ${_safe_float(acct, 'buying_power'):,.2f}")
    print(f"  Cash           : ${_safe_float(acct, 'cash'):,.2f}")
    print(f"  Portfolio Value: ${_safe_float(acct, 'portfolio_value'):,.2f}")
    print(f"  Unrealized P&L : ${_safe_float(acct, 'unrealized_pl'):,.2f}")
    print(f"  Realized P&L   : ${_safe_float(acct, 'realized_pl'):,.2f}")
    print("============================")
    print("[alpaca] Connection OK.")


if __name__ == "__main__":
    main()
