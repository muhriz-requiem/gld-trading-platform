from enum import Enum


class RuntimeMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"   # Disabled by default. Requires explicit override. Never the default.
