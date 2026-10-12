import os
from dataclasses import dataclass
from src.runtime.mode import RuntimeMode


@dataclass
class BrokerConfig:
    """
    Centralized broker configuration.
    No secrets should be read anywhere else in the system.
    """
    api_key: str
    secret_key: str
    base_url: str


@dataclass
class RuntimeConfig:
    """
    Runtime configuration loaded exclusively from environment variables.
    No file I/O. No defaults that enable live trading.
    """

    mode: RuntimeMode
    symbol: str
    strict_mode: bool
    allow_live_trading: bool

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        raw_mode = os.environ.get("RUNTIME_MODE", "backtest").lower()

        try:
            mode = RuntimeMode(raw_mode)
        except ValueError:
            raise ValueError(
                f"Invalid RUNTIME_MODE='{raw_mode}'. "
                f"Allowed values: backtest, paper, live"
            )

        return cls(
            mode=mode,
            symbol=os.environ.get("SYMBOL", "GLD").upper(),
            strict_mode=os.environ.get("STRICT_MODE", "true").lower() == "true",
            allow_live_trading=os.environ.get("ALLOW_LIVE_TRADING", "false").lower() == "true",
        )


def load_broker_config() -> BrokerConfig:
    """
    Loads broker credentials based on runtime mode.
    This is the ONLY place credentials are read.
    """

    mode = os.environ.get("RUNTIME_MODE", "backtest").lower()

    if mode == "paper":
        api_key = os.getenv("ALPACA_API_KEY_PAPER")
        secret = os.getenv("ALPACA_SECRET_KEY_PAPER")
        base_url = "https://paper-api.alpaca.markets"

    elif mode == "live":
        api_key = os.getenv("ALPACA_API_KEY_LIVE")
        secret = os.getenv("ALPACA_SECRET_KEY_LIVE")
        base_url = "https://api.alpaca.markets"

    else:
        raise ValueError(f"Broker config not supported for mode={mode}")

    if not api_key or not secret:
        raise EnvironmentError(f"Missing Alpaca credentials for mode={mode}")

    return BrokerConfig(
        api_key=api_key,
        secret_key=secret,
        base_url=base_url
    )
