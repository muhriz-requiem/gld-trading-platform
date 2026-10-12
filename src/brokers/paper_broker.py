import uuid
from datetime import datetime, timezone
from src.brokers.base import BrokerBase
from src.contracts.order import Order, OrderSide, OrderType, OrderStatus
from src.contracts.position import Position
from src.contracts.signal import Signal, SignalDirection
from src.execution.simulator import ExecutionSimulator


def _signal_to_side(signal: Signal) -> OrderSide | None:
    """Map SignalDirection to OrderSide. Returns None for FLAT (close order)."""
    if signal.direction == SignalDirection.LONG:
        return OrderSide.BUY
    if signal.direction == SignalDirection.SHORT:
        return OrderSide.SELL
    return None  # FLAT → close via opposite side in simulator


class PaperBroker(BrokerBase):
    """
    Paper-only broker wrapping ExecutionSimulator.
    Translates StrategySignal → Order → ExecutionSimulator.process().
    No real API calls. Deterministic. Single-symbol only.
    Supports optional notional-based execution (overrides qty when set).
    """

    def __init__(self) -> None:
        self._simulator = ExecutionSimulator()
        self._orders: dict[str, Order] = {}

    def submit_order(
        self,
        signal: Signal,
        close_price: float,
        notional: float | None = None,
    ) -> Order:
        """
        Translate signal → Order, run through simulator, return filled/rejected Order.
        If notional is set, quantity is set to 0 and notional overrides qty in simulator.
        FLAT signals generate a synthetic SELL order to represent the close.
        """
        side = _signal_to_side(signal)
        if side is None:
            side = OrderSide.SELL  # FLAT represented as close-side sell

        order = Order(
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=0 if notional is not None else ExecutionSimulator.QUANTITY,
            notional=notional,
            status=OrderStatus.PENDING,
            order_id=str(uuid.uuid4()),
            created_at=signal.generated_at,
        )

        fill = self._simulator.process(signal, close_price, notional=notional)

        if fill is not None:
            order.status = OrderStatus.FILLED
            order.filled_price = fill.fill_price
            order.filled_at = fill.filled_at
        else:
            order.status = OrderStatus.REJECTED  # no-op signals become REJECTED

        self._orders[order.order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a PENDING order. Paper broker has no async pending — always False."""
        order = self._orders.get(order_id)
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    def get_positions(self) -> list[Position]:
        state = self._simulator.state()
        if state.position is None:
            return []
        self._simulator.update_price(state.position.current_price)
        return [state.position]

    def get_account_state(self) -> dict:
        state = self._simulator.state()
        return {
            "realized_pnl": state.realized_pnl,
            "unrealized_pnl": self._simulator.unrealized_pnl,
            "fill_count": len(state.fills),
            "open_position": state.position is not None,
        }
