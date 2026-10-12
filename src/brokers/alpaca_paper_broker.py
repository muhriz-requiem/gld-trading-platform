import os
from datetime import datetime, timezone

from src.brokers.base import BrokerBase
from src.contracts.order import Order, OrderSide, OrderType, OrderStatus
from src.contracts.position import Position
from src.contracts.signal import Signal, SignalDirection

SYMBOL = "GLD"

# Paper endpoint ONLY. This broker must never reach the live endpoint.
# tests/test_alpaca_paper_broker.py::test_paper_endpoint_only enforces that the live
# host string does not appear anywhere in this module.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"


# =========================================================
# Credentials (PAPER ONLY)
# =========================================================
def _require_credentials() -> tuple[str, str]:
    key = (
        os.environ.get("ALPACA_API_KEY_PAPER")
        or os.environ.get("ALPACA_API_KEY")
        or ""
    )
    secret = (
        os.environ.get("ALPACA_SECRET_KEY_PAPER")
        or os.environ.get("ALPACA_SECRET_KEY")
        or ""
    )

    if not key or not secret:
        raise EnvironmentError(
            "Missing Alpaca API credentials.\n"
            "Set ALPACA_API_KEY_PAPER and ALPACA_SECRET_KEY_PAPER for paper trading."
        )

    return key, secret


# =========================================================
# Alpaca client
# =========================================================
def _get_alpaca_trading_client():
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        raise ImportError("alpaca-py required: pip install alpaca-py")

    key, secret = _require_credentials()
    # url_override pins the endpoint to paper. Without it, ExecutionRouter passes a
    # BrokerConfig carrying a LIVE base_url to this paper-only broker; the config is
    # stored but never read, so setting STRICT_MODE=false + ALLOW_LIVE_TRADING=true
    # silently yields paper trading with no warning.
    return TradingClient(key, secret, paper=True, url_override=PAPER_BASE_URL)


# =========================================================
# Order mapping
# =========================================================
def _map_signal_to_request(signal: Signal, notional: float | None = None):
    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
    except ImportError:
        raise ImportError("alpaca-py required: pip install alpaca-py")

    if signal.direction == SignalDirection.FLAT:
        return None

    side = (
        AlpacaSide.BUY
        if signal.direction == SignalDirection.LONG
        else AlpacaSide.SELL
    )

    if notional is not None:
        return MarketOrderRequest(
            symbol=SYMBOL,
            notional=round(float(notional), 2),
            side=side,
            time_in_force=TimeInForce.DAY,
        )

    return MarketOrderRequest(
        symbol=SYMBOL,
        qty=1,
        side=side,
        time_in_force=TimeInForce.DAY,
    )


# =========================================================
# Broker implementation
# =========================================================
class AlpacaPaperBroker(BrokerBase):
    """
    Paper trading broker using Alpaca Markets.
    No simulation fallback. No live trading.
    Supports notional execution.
    """

    def __init__(self, config=None):
        self._config = config
        self._client = _get_alpaca_trading_client()

    # -----------------------------------------------------
    # Submit order
    # -----------------------------------------------------
    def submit_order(
        self,
        signal: Signal,
        close_price: float,
        notional: float | None = None,
    ) -> Order:

        ts = signal.generated_at

        order = Order(
            symbol=SYMBOL,
            side=(
                OrderSide.BUY
                if signal.direction == SignalDirection.LONG
                else OrderSide.SELL
            ),
            order_type=OrderType.MARKET,
            quantity=0.0 if notional is not None else 1.0,
            notional=notional,
            created_at=ts,
        )

        try:
            if signal.direction == SignalDirection.FLAT:
                self._client.close_position(SYMBOL)
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.now(tz=timezone.utc)
                return order

            request = _map_signal_to_request(signal, notional)
            response = self._client.submit_order(request)

            order.order_id = str(response.id)
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(tz=timezone.utc)

            order.filled_price = (
                float(response.filled_avg_price)
                if getattr(response, "filled_avg_price", None)
                else None
            )

            print(f"[AlpacaPaperBroker] {signal.direction} order: {order.order_id}")

        except Exception as e:
            order.status = OrderStatus.REJECTED
            print(f"[AlpacaPaperBroker] order rejected: {e}")

        return order

    # -----------------------------------------------------
    # Cancel order
    # -----------------------------------------------------
    def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except Exception as e:
            print(f"[AlpacaPaperBroker] cancel failed: {e}")
            return False

    # -----------------------------------------------------
    # Positions
    # -----------------------------------------------------
    def get_positions(self) -> list[Position]:
        try:
            raw = self._client.get_all_positions()

            return [
                Position(
                    symbol=p.symbol,
                    quantity=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price or 0.0),
                    current_price=float(p.current_price or 0.0),
                )
                for p in raw
                if p.symbol == SYMBOL
            ]

        except Exception as e:
            print(f"[AlpacaPaperBroker] get_positions failed: {e}")
            return []

    # -----------------------------------------------------
    # Account state
    # -----------------------------------------------------
    def get_account_state(self) -> dict:
        try:
            acct = self._client.get_account()

            unrealized = (
                getattr(acct, "unrealized_pl", None)
                or getattr(acct, "unrealized_plpc", None)
                or 0.0
            )

            return {
                "realized_pnl": float(acct.realized_pl or 0.0),
                "unrealized_pnl": float(unrealized),
                "fill_count": None,
                "open_position": len(self.get_positions()) > 0,
                "portfolio_value": float(acct.portfolio_value or 0.0),
                "cash": float(acct.cash or 0.0),
            }

        except Exception as e:
            print(f"[AlpacaPaperBroker] get_account_state failed: {e}")
            return {
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "fill_count": None,
                "open_position": False,
                "portfolio_value": 0.0,
                "cash": 0.0,
            }
