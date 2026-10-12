from abc import ABC, abstractmethod
from src.contracts.signal import Signal


class StrategyInterface(ABC):

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for this strategy."""
        ...

    @abstractmethod
    def generate_signal(self, data: dict) -> Signal:
        """Produce a Signal from the provided feature data."""
        ...
