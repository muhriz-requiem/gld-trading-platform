from dataclasses import dataclass, field
from datetime import datetime
from src.contracts.signal import Signal, SignalDirection
from src.contracts.position import Position


@dataclass
class FillRecord:
    """Immutable record of a single simulated fill."""
    symbol: str
    direction: SignalDirection
    fill_price: float
    filled_at: datetime
    realized_pnl: float        # PnL locked in at close (0.0 for entries)


@dataclass
class SimulatorState:
    """Complete observable state of the simulator at any point."""
    position: Position | None
    realized_pnl: float
    fills: list[FillRecord]


def _resolve_quantity(quantity: float, notional: float | None, close_price: float) -> float:
    """
    Return effective fill quantity.
    If notional is set, derive qty from notional / close_price.
    Otherwise return quantity as-is.
    """
    if notional is not None:
        if close_price <= 0:
            raise ValueError("close_price must be > 0 for notional orders")
        return notional / close_price
    return quantity


class ExecutionSimulator:
    """
    Deterministic single-symbol execution simulator.
    Fills occur at exact bar close price. No slippage. No commissions.
    Single-symbol (GLD). No broker integration. No file I/O.

    State tracked:
        - current Position (or None if flat)
        - cumulative realized PnL
        - ordered fill history
    """

    QUANTITY = 1.0  # fixed unit size — no sizing logic

    def __init__(self) -> None:
        self._position: Position | None = None
        self._realized_pnl: float = 0.0
        self._fills: list[FillRecord] = []

    def process(
        self,
        signal: Signal,
        close_price: float,
        notional: float | None = None,
    ) -> FillRecord | None:
        """
        Process a StrategySignal against the current close price.

        Args:
            signal:      StrategySignal to process.
            close_price: Bar close price used for fill and PnL.
            notional:    If set, overrides QUANTITY with notional / close_price.

        Rules:
            LONG  → open long if flat; no-op if already long
            SHORT → open short if flat; no-op if already short
            FLAT  → close any open position; no-op if already flat

        Returns:
            FillRecord if a fill occurred, None if no-op.
        """
        direction = signal.direction
        ts = signal.generated_at
        qty = _resolve_quantity(self.QUANTITY, notional, close_price)

        # FLAT — close position if open
        if direction == SignalDirection.FLAT:
            if self._position is None:
                return None
            pnl = self._close_position(close_price)
            fill = FillRecord(symbol=signal.symbol, direction=SignalDirection.FLAT,
                              fill_price=close_price, filled_at=ts, realized_pnl=pnl)
            self._fills.append(fill)
            return fill

        # LONG — open if flat, no-op if already long
        if direction == SignalDirection.LONG:
            if self._position is not None and self._position.quantity > 0:
                return None  # already long
            if self._position is not None:
                pnl = self._close_position(close_price)  # close short first
                self._fills.append(FillRecord(signal.symbol, SignalDirection.FLAT,
                                              close_price, ts, pnl))
            self._position = Position(symbol=signal.symbol, quantity=qty,
                                      avg_entry_price=close_price,
                                      current_price=close_price, opened_at=ts)
            fill = FillRecord(signal.symbol, SignalDirection.LONG, close_price, ts, 0.0)
            self._fills.append(fill)
            return fill

        # SHORT — open if flat, no-op if already short
        if direction == SignalDirection.SHORT:
            if self._position is not None and self._position.quantity < 0:
                return None  # already short
            if self._position is not None:
                pnl = self._close_position(close_price)  # close long first
                self._fills.append(FillRecord(signal.symbol, SignalDirection.FLAT,
                                              close_price, ts, pnl))
            self._position = Position(symbol=signal.symbol, quantity=-qty,
                                      avg_entry_price=close_price,
                                      current_price=close_price, opened_at=ts)
            fill = FillRecord(signal.symbol, SignalDirection.SHORT, close_price, ts, 0.0)
            self._fills.append(fill)
            return fill

        return None

    def update_price(self, close_price: float) -> None:
        """Update current_price on open position for unrealized PnL tracking."""
        if self._position is not None:
            self._position.current_price = close_price

    def _close_position(self, close_price: float) -> float:
        """Close current position, return realized PnL."""
        if self._position is None:
            return 0.0
        pnl = (close_price - self._position.avg_entry_price) * self._position.quantity
        self._realized_pnl += pnl
        self._position = None
        return round(pnl, 10)

    def state(self) -> SimulatorState:
        return SimulatorState(
            position=self._position,
            realized_pnl=round(self._realized_pnl, 10),
            fills=list(self._fills),
        )

    @property
    def unrealized_pnl(self) -> float:
        if self._position is None:
            return 0.0
        return self._position.unrealized_pnl
