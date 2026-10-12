import math


def log_return(bars: list[dict], **_) -> dict[str, float]:
    """Log return of the final bar. Requires >= 2 bars."""
    if len(bars) < 2:
        raise ValueError("log_return requires at least 2 bars")
    c_prev = bars[-2]["c"]
    c_curr = bars[-1]["c"]
    return {"log_return_v1": math.log(c_curr / c_prev)}


def rolling_volatility(bars: list[dict], window: int = 20, **_) -> dict[str, float]:
    """Std dev of log returns over trailing window. Requires >= window + 1 bars."""
    if len(bars) < window + 1:
        raise ValueError(f"rolling_volatility requires at least {window + 1} bars")
    window_bars = bars[-(window + 1):]
    returns = [
        math.log(window_bars[i]["c"] / window_bars[i - 1]["c"])
        for i in range(1, len(window_bars))
    ]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)
    return {"rolling_volatility_v1": math.sqrt(variance)}


def momentum(bars: list[dict], window: int = 20, **_) -> dict[str, float]:
    """n-period price momentum: c[t] / c[t-n] - 1. Requires >= window + 1 bars."""
    if len(bars) < window + 1:
        raise ValueError(f"momentum requires at least {window + 1} bars")
    return {"momentum_v1": bars[-1]["c"] / bars[-(window + 1)]["c"] - 1}
