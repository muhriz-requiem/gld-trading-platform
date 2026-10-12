import requests
from datetime import date


ALPACA_BASE_URL = "https://data.alpaca.markets/v2"


class AlpacaHistoricalConnector:
    """Fetches historical bar data from Alpaca Markets."""

    def __init__(self, api_key: str, api_secret: str):
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
        }

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: date,
        end: date,
        limit: int = 1000,
    ) -> list[dict]:
        """
        Fetch OHLCV bars for a symbol.

        Args:
            symbol:    Ticker symbol (e.g. 'GLD')
            timeframe: Bar size string (e.g. '1Day', '1Hour')
            start:     Start date (inclusive)
            end:       End date (inclusive)
            limit:     Max bars per request (Alpaca max: 10000)

        Returns:
            List of bar dicts with keys: t, o, h, l, c, v
        """
        params = {
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": limit,
            "adjustment": "all",
        }

        url = f"{ALPACA_BASE_URL}/stocks/{symbol}/bars"
        response = requests.get(url, headers=self._headers, params=params)
        response.raise_for_status()

        return response.json().get("bars", [])
