"""
scripts/test_single_paper_trade.py

Submits exactly one LONG market order for GLD via AlpacaPaperBroker (paper only).
Prints order id, status, and resulting GLD position.
No loops. No replay. No backtesting. No autonomous trading.
"""

import sys
import os
from datetime import datetime, timezone

# -----------------------------
# Environment bootstrap
# -----------------------------
def _load_dotenv() -> None:
    env_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", ".env")
    )

    if not os.path.exists(env_path):
        print(f"[warn] No .env found at {env_path} — relying on shell environment.")
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(
                key.strip(),
                value.strip().strip('"').strip("'")
            )

_load_dotenv()

# Ensure project root import access
sys.path.insert(
    0,
    os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
)

# -----------------------------
# Core imports
# -----------------------------
from src.runtime.mode import RuntimeMode
from src.runtime.config import RuntimeConfig
from src.runtime.execution_router import ExecutionRouter
from src.brokers.alpaca_paper_broker import AlpacaPaperBroker
from src.contracts.signal import Signal, SignalDirection

# -----------------------------
# Test parameters
# -----------------------------
NOTIONAL = 50.0  # USD-based execution size


def main() -> None:
    # -------------------------
    # Runtime config (PAPER ONLY)
    # -------------------------
    config = RuntimeConfig(
        mode=RuntimeMode.PAPER,
        symbol="GLD",
        strict_mode=True,
        allow_live_trading=False,
    )

    router = ExecutionRouter(config)
    backend = router.get_backend()

    if not isinstance(backend, AlpacaPaperBroker):
        print(f"[error] Wrong backend: {type(backend).__name__}. Aborting.")
        sys.exit(1)

    print(f"[runtime] Mode   : {config.mode.value}")
    print(f"[runtime] Backend: {type(backend).__name__} ✓")

    # -------------------------
    # Deterministic test signal
    # -------------------------
    signal = Signal(
        symbol="GLD",
        direction=SignalDirection.LONG,
        confidence=1.0,
        strategy_id="manual_test_v1",
        generated_at=datetime.now(tz=timezone.utc),
    )

    print(f"[order] Submitting LONG market order for GLD (notional=${NOTIONAL:.2f})...")

    order = backend.submit_order(
        signal,
        close_price=0.0,
        notional=NOTIONAL
    )

    # -------------------------
    # Output result
    # -------------------------
    print()
    print("=== Order Result ===")
    print(f"  Order ID : {order.order_id or 'n/a'}")
    print(f"  Status   : {order.status.value}")
    print(f"  Side     : {order.side.value}")
    print(f"  Notional : ${order.notional:.2f}")
    print(f"  Filled @ : {order.filled_price or 'pending'}")
    print("====================")

    # -------------------------
    # Position check
    # -------------------------
    positions = backend.get_positions()
    gld = next((p for p in positions if p.symbol == "GLD"), None)

    print()
    print("=== GLD Position ===")

    if gld:
        print(f"  Symbol     : {gld.symbol}")
        print(f"  Quantity   : {gld.quantity}")
        print(f"  Avg Entry  : ${gld.avg_entry_price:,.2f}")
        print(f"  Current Px : ${gld.current_price:,.2f}")
        print(f"  Unrealized : ${gld.unrealized_pnl:,.2f}")
    else:
        print("  No GLD position found (order may be pending settlement).")

    print("====================")


if __name__ == "__main__":
    main()
