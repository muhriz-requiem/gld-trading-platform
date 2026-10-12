from abc import ABC, abstractmethod
from typing import Callable


class RealtimeFeedInterface(ABC):
    """Abstract base for all real-time data feeds."""

    @abstractmethod
    def connect(self) -> None:
        """Open connection to the feed."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the feed."""
        ...

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to real-time updates for given symbols."""
        ...

    @abstractmethod
    def on_bar(self, callback: Callable[[dict], None]) -> None:
        """
        Register a callback to receive incoming bar updates.
        Callback receives a bar dict with keys: t, o, h, l, c, v, symbol.
        """
        ...
