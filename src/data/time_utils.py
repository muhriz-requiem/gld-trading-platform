from datetime import datetime, timezone


def to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_alpaca_timestamp(ts: str) -> datetime:
    """Parse Alpaca ISO timestamp string to UTC datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def align_to_timeframe(bars: list[dict], expected_times: list[datetime]) -> list[dict]:
    """
    Align bars to a fixed time grid. Missing bars are dropped.
    Returns only bars whose timestamps match expected_times.
    """
    expected_set = {t.isoformat() for t in expected_times}
    return [b for b in bars if b.get("t") in expected_set]
