from dataclasses import dataclass
from datetime import datetime, timedelta
from src.contracts.signal import Signal, SignalDirection
from src.execution.simulator import SimulatorState, FillRecord


# --- Default hard limits ---
DEFAULT_MAX_POSITION_SIZE: float = 1.0        # max absolute quantity
DEFAULT_MAX_DAILY_LOSS: float = -500.0        # max cumulative daily realized loss
DEFAULT_MAX_DRAWDOWN: float = -1000.0         # max peak-to-trough realized loss
DEFAULT_MAX_CONSECUTIVE_LOSSES: int = 4       # halt after N consecutive losing fills
DEFAULT_EXPOSURE_CAP: float = 1.0             # max directional quantity in either direction
DEFAULT_COOLDOWN_SECONDS: int = 60            # min seconds between accepted trades


@dataclass
class RiskDecision:
    """Output of RiskEngine.evaluate(). Read-only — no execution logic."""
    allowed: bool
    reason: str
    adjusted_size: float | None = None    # only populated when allowed=True


class RiskEngine:
    """
    Deterministic pre-execution risk filter.
    Evaluates StrategySignals BEFORE they reach the broker or simulator.
    Does NOT modify signals. Does NOT execute trades. Does NOT call broker layer.

    Stateful only to the minimum required:
      - tracks last accepted trade timestamp (for cooldown)
      - derives all other checks from SimulatorState passed in at call time
    """

    def __init__(
        self,
        max_position_size: float = DEFAULT_MAX_POSITION_SIZE,
        max_daily_loss: float = DEFAULT_MAX_DAILY_LOSS,
        max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
        max_consecutive_losses: int = DEFAULT_MAX_CONSECUTIVE_LOSSES,
        exposure_cap: float = DEFAULT_EXPOSURE_CAP,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._max_position_size = max_position_size
        self._max_daily_loss = max_daily_loss
        self._max_drawdown = max_drawdown
        self._max_consecutive_losses = max_consecutive_losses
        self._exposure_cap = exposure_cap
        self._cooldown_seconds = cooldown_seconds
        self._last_accepted_at: datetime | None = None
        self._peak_realized_pnl: float = 0.0

    def evaluate(self, signal: Signal, state: SimulatorState) -> RiskDecision:
        """
        Evaluate a StrategySignal against current simulator state.
        Returns RiskDecision. Never raises. Never executes.
        """
        # FLAT signals always pass — closing a position is always allowed
        if signal.direction == SignalDirection.FLAT:
            return RiskDecision(allowed=True, reason="flat_always_allowed",
                                adjusted_size=self._max_position_size)

        # 1. Max position size / exposure cap
        current_qty = abs(state.position.quantity) if state.position else 0.0
        if current_qty >= self._exposure_cap:
            return RiskDecision(allowed=False,
                                reason=f"exposure_cap_reached: {current_qty} >= {self._exposure_cap}")

        # 2. Max daily loss
        if state.realized_pnl <= self._max_daily_loss:
            return RiskDecision(allowed=False,
                                reason=f"max_daily_loss_breached: {state.realized_pnl}")

        # 3. Max drawdown (peak-to-trough on realized PnL)
        self._peak_realized_pnl = max(self._peak_realized_pnl, state.realized_pnl)
        drawdown = state.realized_pnl - self._peak_realized_pnl
        if drawdown <= self._max_drawdown:
            return RiskDecision(allowed=False,
                                reason=f"max_drawdown_breached: drawdown={drawdown:.2f}")

        # 4. Max consecutive losses
        consecutive = _count_consecutive_losses(state.fills)
        if consecutive >= self._max_consecutive_losses:
            return RiskDecision(allowed=False,
                                reason=f"max_consecutive_losses: {consecutive}")

        # 5. Cooldown window
        if self._last_accepted_at is not None:
            elapsed = (signal.generated_at - self._last_accepted_at).total_seconds()
            if elapsed < self._cooldown_seconds:
                return RiskDecision(allowed=False,
                                    reason=f"cooldown_active: {elapsed:.1f}s < {self._cooldown_seconds}s")

        # All checks passed
        self._last_accepted_at = signal.generated_at
        return RiskDecision(allowed=True, reason="all_checks_passed",
                            adjusted_size=self._max_position_size)


def _count_consecutive_losses(fills: list[FillRecord]) -> int:
    """Count trailing consecutive fills with realized_pnl < 0 (entry fills excluded)."""
    count = 0
    for fill in reversed(fills):
        if fill.realized_pnl == 0.0:
            continue  # entry fills — skip
        if fill.realized_pnl < 0:
            count += 1
        else:
            break
    return count
