from dataclasses import dataclass, field
from datetime import datetime, timezone


# Canonical event types — stable, never renamed
EVENT_INVALID_BAR_SKIPPED = "invalid_bar_skipped"
EVENT_FEATURE_GENERATION = "feature_generation"
EVENT_FEATURE_SIGNAL_CREATED = "feature_signal_created"
EVENT_STRATEGY_SIGNAL_CREATED = "strategy_signal_created"


@dataclass
class ReplayEvent:
    """
    Immutable structured replay event. Append-only. Passive observer only.

    Fields:
        timestamp:  UTC-aware datetime of the event
        event_type: One of the canonical EVENT_* constants
        symbol:     Ticker associated with the event (or empty string if N/A)
        stage:      Source stage identifier (e.g. "replay", "feature", "strategy")
        metadata:   Flat dict of additional context — no nested objects
    """
    timestamp: datetime
    event_type: str
    symbol: str
    stage: str
    metadata: dict = field(default_factory=dict)


class ReplayLogger:
    """
    In-memory append-only replay event recorder.
    Passive — cannot modify signals, features, or strategy outputs.
    """

    def __init__(self) -> None:
        self._events: list[ReplayEvent] = []

    def log(
        self,
        event_type: str,
        symbol: str,
        stage: str,
        metadata: dict | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Append a replay event. Timestamp defaults to UTC now if not provided."""
        self._events.append(ReplayEvent(
            timestamp=timestamp or datetime.now(tz=timezone.utc),
            event_type=event_type,
            symbol=symbol,
            stage=stage,
            metadata=metadata or {},
        ))

    def events(self) -> list[ReplayEvent]:
        """Return ordered copy of all recorded events."""
        return list(self._events)

    def count(self) -> int:
        return len(self._events)

    def of_type(self, event_type: str) -> list[ReplayEvent]:
        """Return all events matching a given event_type."""
        return [e for e in self._events if e.event_type == event_type]
