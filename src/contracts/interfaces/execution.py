from abc import ABC, abstractmethod
from src.contracts.order import Order


class ExecutionInterface(ABC):

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order and return it with updated status/ID."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if successful."""
        ...

    @abstractmethod
    def get_order_status(self, order_id: str) -> Order:
        """Fetch current state of an order by ID."""
        ...
