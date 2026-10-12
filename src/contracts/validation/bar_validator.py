from datetime import datetime, timezone


# Required bar fields and their expected types
_REQUIRED_FIELDS: dict[str, type] = {
    "t": str,
    "o": (int, float),
    "h": (int, float),
    "l": (int, float),
    "c": (int, float),
    "v": (int, float),
    "symbol": str,
}


def validate_bar(bar: dict) -> tuple[bool, list[str]]:
    """
    Validate a single bar dict against the canonical bar schema.

    Returns:
        (valid, errors) — valid is True only if errors is empty.
    """
    errors: list[str] = []

    if not isinstance(bar, dict):
        return False, ["bar must be a dict"]

    # Field presence and type checks
    for field, expected_type in _REQUIRED_FIELDS.items():
        if field not in bar:
            errors.append(f"missing required field: '{field}'")
            continue
        if not isinstance(bar[field], expected_type):
            actual = type(bar[field]).__name__
            expected = expected_type.__name__ if isinstance(expected_type, type) else "int|float"
            errors.append(f"field '{field}' must be {expected}, got {actual}")

    # Timestamp UTC check — only if 't' passed type check
    if "t" in bar and isinstance(bar["t"], str):
        try:
            dt = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
            if dt.tzinfo is None or dt.utcoffset() != datetime.fromtimestamp(0, tz=timezone.utc).utcoffset():
                errors.append("field 't' must be a UTC-aware ISO 8601 timestamp")
        except ValueError:
            errors.append(f"field 't' is not a valid ISO 8601 timestamp: '{bar['t']}'")

    return (len(errors) == 0, errors)


def validate_bars(bars: list[dict]) -> tuple[bool, list[str]]:
    """
    Validate a list of bar dicts. Aggregates errors with bar index.

    Returns:
        (valid, errors) — valid is True only if all bars pass.
    """
    all_errors: list[str] = []

    for i, bar in enumerate(bars):
        valid, errors = validate_bar(bar)
        if not valid:
            all_errors.extend([f"bar[{i}]: {e}" for e in errors])

    return (len(all_errors) == 0, all_errors)
