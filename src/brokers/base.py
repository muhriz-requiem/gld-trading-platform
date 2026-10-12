from abc import ABC, abstractmethod
from src.contracts.order import Order
from src.contracts.position import Position
from src.contracts.signal import Signal


class BrokerBase(ABC):
    """
    Abstract broker interface. Execution-agnostic.
    PaperBroker and future AlpacaBroker are drop-in implementations.
    No strategy logic. No risk logic. Translation layer only.
    """

    @abstractmethod
    def submit_order(self, signal: Signal, close_price: float) -> Order:
        """Translate a StrategySignal into a broker order and submit it."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order by ID. Returns True if successful."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return current open positions."""
        ...

    @abstractmethod
    def get_account_state(self) -> dict:
        """Return flat dict of account state: realized_pnl, unrealized_pnl, fill_count."""
        ...
