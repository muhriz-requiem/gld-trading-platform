from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PositionSnapshot:
    """Single position as reported by Alpaca."""
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "qty": self.qty,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
        }


@dataclass(frozen=True)
class OrderSnapshot:
    """Single open/recent order as reported by Alpaca."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    qty: float | None
    notional: float | None
    status: str
    filled_qty: float
    filled_avg_price: float | None
    submitted_at: datetime | None
    filled_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "qty": self.qty,
            "notional": self.notional,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "filled_avg_price": self.filled_avg_price,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


@dataclass(frozen=True)
class AccountSnapshot:
    """Account-level financials as reported by Alpaca."""
    portfolio_value: float
    cash: float
    buying_power: float
    equity: float
    last_equity: float
    realized_pnl: float
    unrealized_pnl: float
    day_trade_count: int
    pattern_day_trader: bool
    account_blocked: bool
    trading_blocked: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_value": self.portfolio_value,
            "cash": self.cash,
            "buying_power": self.buying_power,
            "equity": self.equity,
            "last_equity": self.last_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "day_trade_count": self.day_trade_count,
            "pattern_day_trader": self.pattern_day_trader,
            "account_blocked": self.account_blocked,
            "trading_blocked": self.trading_blocked,
            "status": self.status,
        }


@dataclass(frozen=True)
class TradeSnapshot:
    """Single recent trade (execution) as reported by Alpaca."""
    trade_id: str
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    executed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "price": self.price,
            "executed_at": self.executed_at.isoformat(),
        }


@dataclass(frozen=True)
class PortfolioStateSnapshot:
    """Complete broker truth at a single instant.

    Source of truth : Alpaca paper trading API.
    Immutable (frozen dataclass). JSON-serialisable via to_dict() / to_json().

    Fields
    ------
    positions      : all open positions reported by Alpaca
    open_orders    : all non-terminal orders (new / partially_filled)
    account_state  : account-level financial summary
    unrealized_pnl : sum of unrealized PnL across all positions
    timestamp      : UTC instant this snapshot was captured
    latest_trades  : recent executions (may be empty if none in window)
    """

    positions: tuple[PositionSnapshot, ...]
    open_orders: tuple[OrderSnapshot, ...]
    account_state: AccountSnapshot
    unrealized_pnl: float
    timestamp: datetime
    latest_trades: tuple[TradeSnapshot, ...] = field(default_factory=tuple)

    def position_for(self, symbol: str) -> PositionSnapshot | None:
        """Return the position for symbol, or None if flat."""
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None

    def open_orders_for(self, symbol: str) -> tuple[OrderSnapshot, ...]:
        """Return all open orders for symbol."""
        return tuple(o for o in self.open_orders if o.symbol == symbol)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "unrealized_pnl": self.unrealized_pnl,
            "account_state": self.account_state.to_dict(),
            "positions": [p.to_dict() for p in self.positions],
            "open_orders": [o.to_dict() for o in self.open_orders],
            "latest_trades": [t.to_dict() for t in self.latest_trades],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def __repr__(self) -> str:
        return (
            f"PortfolioStateSnapshot("
            f"ts={self.timestamp.isoformat()}, "
            f"positions={len(self.positions)}, "
            f"open_orders={len(self.open_orders)}, "
            f"unrealized_pnl={self.unrealized_pnl:.4f}"
            f")"
        )
