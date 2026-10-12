"""
alpaca_adapter.py  -  Stage 14.2: Portfolio State Reconciler
=============================================================
AlpacaStateAdapter: read-only wrapper around the Alpaca
TradingClient that returns typed snapshot objects.

Design rules:
  - paper trading ONLY (paper=True hardcoded)
  - NO caching, NO write operations, NO order submission
  - NO imports from execution / strategy / risk layers
  - every method returns immutable value objects from snapshot.py
  - raises AlpacaAdapterError on credential / API failures
    (never silently swallows errors so the reconciler can log them)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.portfolio.snapshot import (
    AccountSnapshot,
    OrderSnapshot,
    PortfolioStateSnapshot,
    PositionSnapshot,
    TradeSnapshot,
)


class AlpacaAdapterError(RuntimeError):
    """Raised when the adapter cannot communicate with Alpaca."""


def _load_credentials() -> tuple[str, str]:
    key = (
        os.environ.get("ALPACA_API_KEY_PAPER")
        or os.environ.get("ALPACA_API_KEY")
        or ""
    )
    secret = (
        os.environ.get("ALPACA_SECRET_KEY_PAPER")
        or os.environ.get("ALPACA_SECRET_KEY")
        or ""
    )
    if not key or not secret:
        raise AlpacaAdapterError(
            "Missing Alpaca credentials for PSR adapter. "
            "Set ALPACA_API_KEY_PAPER and ALPACA_SECRET_KEY_PAPER."
        )
    return key, secret


def _build_trading_client():
    try:
        from alpaca.trading.client import TradingClient  # type: ignore[import]
    except ImportError as exc:
        raise AlpacaAdapterError("alpaca-py not installed. Run: pip install alpaca-py") from exc
    key, secret = _load_credentials()
    return TradingClient(key, secret, paper=True)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _to_utc(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _map_position(raw) -> PositionSnapshot:
    return PositionSnapshot(
        symbol=str(raw.symbol),
        qty=_safe_float(raw.qty),
        avg_entry_price=_safe_float(raw.avg_entry_price),
        current_price=_safe_float(getattr(raw, "current_price", None)),
        market_value=_safe_float(getattr(raw, "market_value", None)),
        unrealized_pnl=_safe_float(getattr(raw, "unrealized_pl", None)),
        unrealized_pnl_pct=_safe_float(getattr(raw, "unrealized_plpc", None)),
    )


def _map_order(raw) -> OrderSnapshot:
    return OrderSnapshot(
        order_id=str(raw.id),
        symbol=str(raw.symbol),
        side=str(raw.side.value if hasattr(raw.side, "value") else raw.side),
        order_type=str(raw.type.value if hasattr(raw.type, "value") else raw.type),
        qty=_safe_float(getattr(raw, "qty", None)) or None,
        notional=_safe_float(getattr(raw, "notional", None)) or None,
        status=str(raw.status.value if hasattr(raw.status, "value") else raw.status),
        filled_qty=_safe_float(getattr(raw, "filled_qty", None)),
        filled_avg_price=(
            _safe_float(raw.filled_avg_price)
            if getattr(raw, "filled_avg_price", None) is not None
            else None
        ),
        submitted_at=_to_utc(getattr(raw, "submitted_at", None)),
        filled_at=_to_utc(getattr(raw, "filled_at", None)),
    )


def _map_account(raw) -> AccountSnapshot:
    unrealized = _safe_float(
        getattr(raw, "unrealized_pl", None)
        or getattr(raw, "unrealized_plpc", None)
    )
    return AccountSnapshot(
        portfolio_value=_safe_float(getattr(raw, "portfolio_value", None)),
        cash=_safe_float(getattr(raw, "cash", None)),
        buying_power=_safe_float(getattr(raw, "buying_power", None)),
        equity=_safe_float(getattr(raw, "equity", None)),
        last_equity=_safe_float(getattr(raw, "last_equity", None)),
        realized_pnl=_safe_float(getattr(raw, "realized_pl", None)),
        unrealized_pnl=unrealized,
        day_trade_count=_safe_int(getattr(raw, "daytrade_count", None)),
        pattern_day_trader=_safe_bool(getattr(raw, "pattern_day_trader", None)),
        account_blocked=_safe_bool(getattr(raw, "account_blocked", None)),
        trading_blocked=_safe_bool(getattr(raw, "trading_blocked", None)),
        status=str(getattr(raw, "status", "unknown")),
    )


def _map_trade(raw) -> TradeSnapshot:
    return TradeSnapshot(
        trade_id=str(getattr(raw, "id", "") or ""),
        order_id=str(getattr(raw, "order_id", "") or ""),
        symbol=str(raw.symbol),
        side=str(raw.side.value if hasattr(raw.side, "value") else raw.side),
        qty=_safe_float(getattr(raw, "qty", None)),
        price=_safe_float(getattr(raw, "price", None)),
        executed_at=_to_utc(getattr(raw, "transaction_time", None))
                    or datetime.now(tz=timezone.utc),
    )


class AlpacaStateAdapter:
    """
    Read-only wrapper around Alpaca TradingClient.

    All methods are stateless: each call creates a fresh API request.
    NO caching. NO mutation. NO order submission capability.
    Paper trading only (enforced at client construction).

    Usage
    -----
        adapter = AlpacaStateAdapter()
        positions = adapter.fetch_positions()
        orders    = adapter.fetch_orders()
        account   = adapter.fetch_account()
        trades    = adapter.fetch_latest_trades("GLD")
        snapshot  = adapter.build_snapshot("GLD")
    """

    def __init__(self) -> None:
        self._client = _build_trading_client()

    def fetch_positions(self) -> tuple[PositionSnapshot, ...]:
        """Fetch all open positions. Returns empty tuple if flat."""
        try:
            raw = self._client.get_all_positions()
            return tuple(_map_position(p) for p in raw)
        except Exception as exc:
            raise AlpacaAdapterError(f"fetch_positions failed: {exc}") from exc

    def fetch_orders(
        self,
        status: str = "open",
        limit: int = 100,
    ) -> tuple[OrderSnapshot, ...]:
        """
        Fetch orders. status: "open" | "closed" | "all".
        Returns empty tuple if no orders match.
        """
        try:
            from alpaca.trading.requests import GetOrdersRequest  # type: ignore[import]
            from alpaca.trading.enums import QueryOrderStatus     # type: ignore[import]
            status_map = {
                "open":   QueryOrderStatus.OPEN,
                "closed": QueryOrderStatus.CLOSED,
                "all":    QueryOrderStatus.ALL,
            }
            query_status = status_map.get(status, QueryOrderStatus.OPEN)
            request = GetOrdersRequest(status=query_status, limit=limit)
            raw = self._client.get_orders(filter=request)
            return tuple(_map_order(o) for o in raw)
        except AlpacaAdapterError:
            raise
        except Exception as exc:
            raise AlpacaAdapterError(f"fetch_orders failed: {exc}") from exc

    def fetch_account(self) -> AccountSnapshot:
        """Fetch account-level financial state."""
        try:
            raw = self._client.get_account()
            return _map_account(raw)
        except Exception as exc:
            raise AlpacaAdapterError(f"fetch_account failed: {exc}") from exc

    def fetch_latest_trades(
        self,
        symbol: str,
        lookback_minutes: int = 60,
    ) -> tuple[TradeSnapshot, ...]:
        """
        Fetch recent fills for *symbol* as TradeSnapshots.
        Uses closed orders as proxy (TradingClient has no /trades endpoint).
        Filters to fills within lookback_minutes.
        """
        try:
            from alpaca.trading.requests import GetOrdersRequest  # type: ignore[import]
            from alpaca.trading.enums import QueryOrderStatus     # type: ignore[import]
            request = GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                symbols=[symbol],
                limit=50,
            )
            raw_orders = self._client.get_orders(filter=request)
            cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=lookback_minutes)
            trades: list[TradeSnapshot] = []
            for o in raw_orders:
                filled_at = _to_utc(getattr(o, "filled_at", None))
                status_val = str(
                    o.status.value if hasattr(o.status, "value") else o.status
                ).lower()
                if status_val != "filled":
                    continue
                if filled_at and filled_at < cutoff:
                    continue
                trades.append(_map_trade(o))
            return tuple(trades)
        except AlpacaAdapterError:
            raise
        except Exception as exc:
            raise AlpacaAdapterError(f"fetch_latest_trades failed: {exc}") from exc

    def build_snapshot(self, symbol: str) -> PortfolioStateSnapshot:
        """
        Build a complete PortfolioStateSnapshot in one call.
        Calls all four fetch methods and assembles the result.
        """
        positions     = self.fetch_positions()
        open_orders   = self.fetch_orders(status="open")
        account_state = self.fetch_account()
        latest_trades = self.fetch_latest_trades(symbol)
        unrealized_pnl = sum(
            p.unrealized_pnl for p in positions if p.symbol == symbol
        )
        return PortfolioStateSnapshot(
            positions=positions,
            open_orders=open_orders,
            account_state=account_state,
            unrealized_pnl=unrealized_pnl,
            timestamp=datetime.now(tz=timezone.utc),
            latest_trades=latest_trades,
        )
