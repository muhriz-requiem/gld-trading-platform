from src.features.kernel import log_return, rolling_volatility, momentum

# Signal registry: maps stable signal name → feature function reference + params.
# No execution logic. No strategy logic. Definitions only.
#
# Each entry defines:
#   "feature_fn"  — function from src.features.kernel
#   "feature_key" — output key produced by that function
#   "params"      — kwargs passed to the feature function

SIGNAL_REGISTRY: dict[str, dict] = {
    "signal_log_return_v1": {
        "feature_fn": log_return,
        "feature_key": "log_return_v1",
        "params": {},
    },
    "signal_rolling_volatility_v1": {
        "feature_fn": rolling_volatility,
        "feature_key": "rolling_volatility_v1",
        "params": {"window": 20},
    },
    "signal_momentum_v1": {
        "feature_fn": momentum,
        "feature_key": "momentum_v1",
        "params": {"window": 20},
    },
}
