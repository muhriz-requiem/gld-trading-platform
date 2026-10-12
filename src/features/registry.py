from src.features import kernel

# Canonical feature names — permanent, never renamed after first use
FEATURE_NAMES = {
    "log_return_v1": "log_return_v1",
    "rolling_volatility_v1": "rolling_volatility_v1",
    "momentum_v1": "momentum_v1",
}

# Version → function reference mapping
FEATURE_REGISTRY: dict[str, callable] = {
    "log_return_v1": kernel.log_return,
    "rolling_volatility_v1": kernel.rolling_volatility,
    "momentum_v1": kernel.momentum,
}
