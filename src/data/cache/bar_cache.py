import json
import os
from datetime import date
from pathlib import Path


CACHE_DIR = Path("runtime/cache")


class LocalBarCache:
    """
    Simple file-based cache for historical bar data.
    Key: {symbol}_{timeframe}_{start}_{end}.json
    """

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, symbol: str, timeframe: str, start: date, end: date) -> Path:
        filename = f"{symbol}_{timeframe}_{start}_{end}.json"
        return self._dir / filename

    def get(self, symbol: str, timeframe: str, start: date, end: date) -> list[dict] | None:
        path = self._key(symbol, timeframe, start, end)
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None

    def set(self, symbol: str, timeframe: str, start: date, end: date, bars: list[dict]) -> None:
        path = self._key(symbol, timeframe, start, end)
        with open(path, "w") as f:
            json.dump(bars, f)
