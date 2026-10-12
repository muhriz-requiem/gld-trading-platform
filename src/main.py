"""
main.py — System entry point.
Loads runtime config, routes to correct backend, runs in selected mode.
Contains no trading logic.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.runtime.config import RuntimeConfig
from src.runtime.execution_router import ExecutionRouter
from src.runtime.mode import RuntimeMode


def main() -> None:
    config = RuntimeConfig.from_env()
    router = ExecutionRouter(config)
    backend = router.get_backend()

    print(f"[main] Runtime mode: {config.mode.value}")
    print(f"[main] Symbol: {config.symbol}")

    if config.mode == RuntimeMode.BACKTEST:
        # Minimal synthetic bar set for smoke-run — real data wired via data layer
        bars: list[dict] = []
        result = backend.run(bars)
        print(f"[main] Backtest complete. Signals: {len(result.signals)}, "
              f"Trades: {len(result.trades)}, "
              f"PnL: {result.evaluation_metrics['final_realized_pnl']}")

    elif config.mode in (RuntimeMode.PAPER, RuntimeMode.LIVE):
        state = backend.get_account_state()
        print(f"[main] Account state: {state}")

    else:
        raise RuntimeError(f"Unhandled mode: {config.mode}")


if __name__ == "__main__":
    main()
