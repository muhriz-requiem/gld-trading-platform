"""
reconciler.py  -  Stage 14.2: Portfolio State Reconciler
=========================================================
reconcile(): deterministic, read-only reconciliation function between
internal system state (plain dicts / snapshots) and Alpaca truth.

Design rules:
  - NO dependency on execution, strategy, risk, or broker modules
  - inputs treated as generic dicts or PortfolioStateSnapshot objects
  - NO side effects, NO mutations, NO trade triggering
  - drift detection is fully deterministic given the same inputs
  - returns (reconciled_snapshot, drift_report) as pure data

DriftReport format (list of dicts):
  [
    {
      "type": str,           # e.g. "missing_fill", "qty_mismatch"
      "symbol": str,
      "internal_value": any,
      "alpaca_value": any,
      "severity": "low" | "medium" | "high"
    }
  ]

Drift types detected:
  A. missing_fill         - trade in Alpaca not reflected internally
  B. qty_mismatch         - position size differs
  C. order_status_mismatch - order status differs
  D. stale_snapshot       - snapshot older than staleness threshold
  E. unexpected_position  - Alpaca has position, internal shows none
  F. missing_position     - internal claims position, Alpaca shows none
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from src.portfolio.snapshot import PortfolioStateSnapshot

logger = logging.getLogger(__name__)

# Type aliases for clarity
DriftEntry = dict[str, Any]
DriftReport = list[DriftEntry]

# Default thresholds
_DEFAULT_QTY_TOLERANCE: float = 1e-4      # fractional shares tolerance
_DEFAULT_STALE_SECONDS: int   = 300       # 5 minutes


# ---------------------------------------------------------------------------
# Private drift-entry builders
# ---------------------------------------------------------------------------

def _entry(
    drift_type: str,
    symbol: str,
    internal_value: Any,
    alpaca_value: Any,
    severity: str,
) -> DriftEntry:
    """Construct a single normalised drift entry."""
    assert severity in ("low", "medium", "high"), f"Invalid severity: {severity}"
    return {
        "type": drift_type,
        "symbol": symbol,
        "internal_value": internal_value,
        "alpaca_value": alpaca_value,
        "severity": severity,
    }


# ---------------------------------------------------------------------------
# Individual drift detectors
# (each returns a list of DriftEntry - empty list means no drift)
# ---------------------------------------------------------------------------

def _detect_stale_snapshot(
    alpaca_snapshot: PortfolioStateSnapshot,
    stale_seconds: int,
) -> DriftReport:
    """
    D. Stale snapshot: snapshot timestamp is older than stale_seconds.
    Severity: low if <= 2x threshold, high if > 2x.
    """
    now = datetime.now(tz=timezone.utc)
    age = (now - alpaca_snapshot.timestamp).total_seconds()
    if age <= stale_seconds:
        return []
    severity = "high" if age > stale_seconds * 2 else "low"
    return [_entry(
        drift_type="stale_snapshot",
        symbol="*",
        internal_value=None,
        alpaca_value=alpaca_snapshot.timestamp.isoformat(),
        severity=severity,
    )]


def _detect_qty_mismatch(
    symbol: str,
    internal_positions: dict[str, float],
    alpaca_snapshot: PortfolioStateSnapshot,
    qty_tolerance: float,
) -> DriftReport:
    """
    B. Position quantity mismatch between internal state and Alpaca.
    Also covers:
      E. unexpected_position  - Alpaca has position, internal shows 0 / missing
      F. missing_position     - internal claims position, Alpaca shows 0 / missing
    """
    report: DriftReport = []
    alpaca_position = alpaca_snapshot.position_for(symbol)
    alpaca_qty = alpaca_position.qty if alpaca_position else 0.0
    internal_qty = internal_positions.get(symbol, 0.0)

    if abs(alpaca_qty - internal_qty) <= qty_tolerance:
        return []

    # Classify sub-type
    if internal_qty == 0.0 and alpaca_qty != 0.0:
        drift_type = "unexpected_position"
        severity   = "high"
    elif internal_qty != 0.0 and alpaca_qty == 0.0:
        drift_type = "missing_position"
        severity   = "high"
    else:
        drift_type = "qty_mismatch"
        # Severity scales with relative difference
        rel_diff = abs(alpaca_qty - internal_qty) / max(abs(alpaca_qty), 1e-9)
        severity = "high" if rel_diff > 0.1 else "medium"

    report.append(_entry(
        drift_type=drift_type,
        symbol=symbol,
        internal_value=internal_qty,
        alpaca_value=alpaca_qty,
        severity=severity,
    ))
    return report


def _detect_missing_fills(
    symbol: str,
    internal_fill_ids: set[str],
    alpaca_snapshot: PortfolioStateSnapshot,
) -> DriftReport:
    """
    A. Missing fills: trades recorded in Alpaca not present in internal state.
    Severity: medium per missing fill; high if > 1 fill missing.
    """
    report: DriftReport = []
    alpaca_fills = [t for t in alpaca_snapshot.latest_trades if t.symbol == symbol]
    missing = [t for t in alpaca_fills if t.trade_id not in internal_fill_ids]
    if not missing:
        return []
    severity = "high" if len(missing) > 1 else "medium"
    for trade in missing:
        report.append(_entry(
            drift_type="missing_fill",
            symbol=symbol,
            internal_value=None,
            alpaca_value={
                "trade_id": trade.trade_id,
                "order_id": trade.order_id,
                "side":     trade.side,
                "qty":      trade.qty,
                "price":    trade.price,
                "executed_at": trade.executed_at.isoformat(),
            },
            severity=severity,
        ))
    return report


def _detect_order_status_mismatch(
    symbol: str,
    internal_orders: dict[str, str],
    alpaca_snapshot: PortfolioStateSnapshot,
) -> DriftReport:
    """
    C. Order status mismatch between internal state and Alpaca.
    internal_orders: {order_id: status_str}
    Severity: high if Alpaca shows cancelled/rejected but internal shows pending.
              medium for other status differences.
    """
    report: DriftReport = []
    alpaca_orders = {o.order_id: o for o in alpaca_snapshot.open_orders if o.symbol == symbol}

    for order_id, int_status in internal_orders.items():
        alp_order = alpaca_orders.get(order_id)
        if alp_order is None:
            # Internal thinks order is open; Alpaca has no open record for it.
            # Could be filled, cancelled, or expired.
            report.append(_entry(
                drift_type="order_status_mismatch",
                symbol=symbol,
                internal_value=int_status,
                alpaca_value="not_in_open_orders",
                severity="medium",
            ))
            continue
        alp_status = alp_order.status
        if alp_status.lower() != int_status.lower():
            severe = alp_status.lower() in ("cancelled", "rejected", "expired")
            report.append(_entry(
                drift_type="order_status_mismatch",
                symbol=symbol,
                internal_value=int_status,
                alpaca_value=alp_status,
                severity="high" if severe else "medium",
            ))
    return report


# ---------------------------------------------------------------------------
# Internal state normaliser
# ---------------------------------------------------------------------------

def _normalise_internal_state(internal_state: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise the internal_state dict to a canonical shape so the
    reconciler is tolerant of varying caller conventions.

    Expected keys (all optional, defaults to empty/neutral values):
        positions  : dict[symbol, float]   e.g. {"GLD": 1.0}
        fill_ids   : set[str] | list[str]  known fill/trade IDs
        orders     : dict[order_id, status_str]
        symbol     : str  (primary symbol being tracked)
    """
    return {
        "positions": dict(internal_state.get("positions") or {}),
        "fill_ids":  set(internal_state.get("fill_ids") or []),
        "orders":    dict(internal_state.get("orders") or {}),
        "symbol":    str(internal_state.get("symbol") or "GLD"),
    }


# ---------------------------------------------------------------------------
# Public reconcile function
# ---------------------------------------------------------------------------

def reconcile(
    internal_state: dict[str, Any],
    alpaca_snapshot: PortfolioStateSnapshot,
    qty_tolerance: float = _DEFAULT_QTY_TOLERANCE,
    stale_seconds: int   = _DEFAULT_STALE_SECONDS,
) -> tuple[PortfolioStateSnapshot, DriftReport]:
    """
    Compare internal system state against Alpaca broker truth.

    Parameters
    ----------
    internal_state : dict with optional keys:
        "symbol"    -> str   primary symbol (default "GLD")
        "positions" -> dict[symbol, float]  qty per symbol
        "fill_ids"  -> set[str]  known trade/fill IDs
        "orders"    -> dict[order_id, status_str]  internal order state

    alpaca_snapshot : PortfolioStateSnapshot
        Broker truth captured via AlpacaStateAdapter.build_snapshot().
        This is the reference - internal state is compared against it.

    qty_tolerance : float
        Absolute qty difference below which positions are considered equal.
        Default 1e-4 (accounts for fractional-share rounding).

    stale_seconds : int
        Snapshot age (seconds) beyond which a staleness drift is emitted.
        Default 300 (5 minutes).

    Returns
    -------
    (reconciled_snapshot, drift_report)

    reconciled_snapshot : PortfolioStateSnapshot
        The Alpaca snapshot, unchanged. Alpaca is truth.
        Returned as-is so the caller always has a reference to broker state.

    drift_report : DriftReport  (list[dict])
        Zero or more drift entries describing every detected discrepancy.
        Empty list means internal state matches Alpaca exactly.
        Sorted by severity descending: high -> medium -> low.
    """
    norm = _normalise_internal_state(internal_state)
    symbol       = norm["symbol"]
    positions    = norm["positions"]
    fill_ids     = norm["fill_ids"]
    orders       = norm["orders"]

    report: DriftReport = []

    # --- D. Stale snapshot
    report.extend(_detect_stale_snapshot(alpaca_snapshot, stale_seconds))

    # --- B/E/F. Position quantity / existence mismatches
    report.extend(_detect_qty_mismatch(symbol, positions, alpaca_snapshot, qty_tolerance))

    # --- A. Missing fills
    report.extend(_detect_missing_fills(symbol, fill_ids, alpaca_snapshot))

    # --- C. Order status mismatches
    report.extend(_detect_order_status_mismatch(symbol, orders, alpaca_snapshot))

    # Sort: high first, then medium, then low
    _severity_rank = {"high": 0, "medium": 1, "low": 2}
    report.sort(key=lambda e: _severity_rank.get(e["severity"], 9))

    # Log summary
    if report:
        high_count   = sum(1 for e in report if e["severity"] == "high")
        medium_count = sum(1 for e in report if e["severity"] == "medium")
        low_count    = sum(1 for e in report if e["severity"] == "low")
        logger.warning(
            "[PSR] Drift detected for %s: %d high, %d medium, %d low",
            symbol, high_count, medium_count, low_count,
        )
        for entry in report:
            logger.debug("[PSR] %s", entry)
    else:
        logger.info("[PSR] No drift detected for %s", symbol)

    # Alpaca snapshot is returned unchanged - it is the truth
    return alpaca_snapshot, report


# ---------------------------------------------------------------------------
# Usage example (comments only - no runtime wiring)
# ---------------------------------------------------------------------------
#
# from src.portfolio.alpaca_adapter import AlpacaStateAdapter
# from src.portfolio.reconciler import reconcile
#
# # 1. Capture broker truth
# adapter  = AlpacaStateAdapter()
# snapshot = adapter.build_snapshot("GLD")
#
# # 2. Build internal state dict from whatever internal source you have
# #    (e.g. from ExecutionSimulator.state() or a cached order book)
# internal = {
#     "symbol":    "GLD",
#     "positions": {"GLD": simulator_state.position.quantity
#                          if simulator_state.position else 0.0},
#     "fill_ids":  {f.trade_id for f in known_fills},
#     "orders":    {o.order_id: o.status for o in tracked_orders},
# }
#
# # 3. Reconcile
# reconciled_snapshot, drift_report = reconcile(internal, snapshot)
#
# # 4. Inspect
# if drift_report:
#     for entry in drift_report:
#         print(entry)
# else:
#     print("Clean: internal state matches Alpaca")
