from src.contracts.signal import Signal, SignalDirection


def directional_accuracy(signals: list[Signal], returns: list[float]) -> float:
    """
    Fraction of non-FLAT signals where predicted direction matches realized return sign.
    LONG correct if return > 0. SHORT correct if return < 0.
    Ignores FLAT signals.

    Raises:
        ValueError: if signals and returns lengths differ.
    """
    if len(signals) != len(returns):
        raise ValueError("signals and returns must have equal length")

    active = [
        (s, r) for s, r in zip(signals, returns)
        if s.direction != SignalDirection.FLAT
    ]
    if not active:
        return 0.0

    correct = sum(
        1 for s, r in active
        if (s.direction == SignalDirection.LONG and r > 0)
        or (s.direction == SignalDirection.SHORT and r < 0)
    )
    return correct / len(active)


def signal_frequency(signals: list[Signal]) -> dict[str, float]:
    """
    Fraction of signals that are LONG, SHORT, and FLAT.
    Returns proportions summing to 1.0.
    """
    if not signals:
        return {"long": 0.0, "short": 0.0, "flat": 0.0}

    n = len(signals)
    counts = {SignalDirection.LONG: 0, SignalDirection.SHORT: 0, SignalDirection.FLAT: 0}
    for s in signals:
        counts[s.direction] += 1

    return {
        "long": counts[SignalDirection.LONG] / n,
        "short": counts[SignalDirection.SHORT] / n,
        "flat": counts[SignalDirection.FLAT] / n,
    }


def average_confidence(signals: list[Signal]) -> float:
    """
    Mean confidence across all signals. Returns 0.0 for empty input.
    """
    if not signals:
        return 0.0
    return sum(s.confidence for s in signals) / len(signals)


def long_short_distribution(signals: list[Signal]) -> dict[str, int]:
    """
    Raw counts of LONG, SHORT, and FLAT signals.
    """
    counts = {"long": 0, "short": 0, "flat": 0}
    for s in signals:
        if s.direction == SignalDirection.LONG:
            counts["long"] += 1
        elif s.direction == SignalDirection.SHORT:
            counts["short"] += 1
        else:
            counts["flat"] += 1
    return counts
