from dataclasses import dataclass, field
from src.contracts.signal import Signal, SignalDirection
from src.contracts.validation.bar_validator import validate_bar
from src.signals.signal_schema import FeatureSignal
from src.signals.signal_registry import SIGNAL_REGISTRY
from src.strategies.baseline_momentum import generate as momentum_strategy
from src.execution.simulator import ExecutionSimulator, FillRecord
from src.risk.risk_engine import RiskEngine, RiskDecision
from src.evaluation.signal_evaluator import (
    directional_accuracy, signal_frequency, average_confidence, long_short_distribution
)
from src.data.time_utils import parse_alpaca_timestamp
from src.observability.replay_logger import ReplayLogger

_MIN_WINDOW = 21


@dataclass
class EquityPoint:
    timestamp: object    # datetime
    realized_pnl: float
    unrealized_pnl: float


@dataclass
class RiskEvent:
    timestamp: object    # datetime
    reason: str
    signal_direction: str


@dataclass
class BacktestResult:
    signals: list[Signal]
    trades: list[FillRecord]
    equity_curve: list[EquityPoint]
    risk_events: list[RiskEvent]
    evaluation_metrics: dict


class BacktestRunner:
    """
    Unified orchestration layer. Coordinates all subsystems in strict deterministic order.
    Does not introduce trading logic. Composes existing components only.

    Execution order per bar:
      1. Validate bar
      2. Accumulate rolling window
      3. Compute features via SIGNAL_REGISTRY
      4. Generate FeatureSignals
      5. Generate StrategySignal
      6. RiskEngine evaluates signal
      7. If allowed → ExecutionSimulator processes
      8. Equity curve + evaluation updated
    """

    def __init__(
        self,
        risk_engine: RiskEngine | None = None,
        logger: ReplayLogger | None = None,
    ) -> None:
        self._risk = risk_engine or RiskEngine()
        self._sim = ExecutionSimulator()
        self._logger = logger

    def run(self, bars: list[dict]) -> BacktestResult:
        signals: list[Signal] = []
        equity_curve: list[EquityPoint] = []
        risk_events: list[RiskEvent] = []
        window: list[dict] = []

        for bar in bars:
            valid, _ = validate_bar(bar)
            if not valid:
                continue

            window.append(bar)
            if len(window) < _MIN_WINDOW:
                continue

            ts = parse_alpaca_timestamp(bar["t"])
            symbol = bar["symbol"]
            close = bar["c"]

            # Step 3–4: Features → FeatureSignals
            feature_signals: list[FeatureSignal] = []
            for signal_name, entry in SIGNAL_REGISTRY.items():
                try:
                    feature_map = entry["feature_fn"](window, **entry["params"])
                    value = feature_map[entry["feature_key"]]
                    feature_signals.append(FeatureSignal(
                        timestamp=ts, symbol=symbol,
                        signal_name=signal_name, value=value, confidence=0.5,
                    ))
                except ValueError:
                    continue

            if not feature_signals:
                continue

            # Step 5: Strategy signal
            try:
                signal = momentum_strategy(feature_signals)
            except ValueError:
                continue

            signals.append(signal)

            # Step 6: Risk evaluation
            sim_state = self._sim.state()
            decision: RiskDecision = self._risk.evaluate(signal, sim_state)

            if not decision.allowed:
                risk_events.append(RiskEvent(
                    timestamp=ts,
                    reason=decision.reason,
                    signal_direction=str(signal.direction),
                ))
                # Update price for unrealized PnL even if blocked
                self._sim.update_price(close)
            else:
                # Step 7: Execute
                self._sim.process(signal, close)
                self._sim.update_price(close)

            # Step 8: Equity snapshot
            state = self._sim.state()
            equity_curve.append(EquityPoint(
                timestamp=ts,
                realized_pnl=state.realized_pnl,
                unrealized_pnl=self._sim.unrealized_pnl,
            ))

        # Collect final trades and metrics
        final_state = self._sim.state()
        trades = final_state.fills

        realized_returns = [f.realized_pnl for f in trades if f.realized_pnl != 0.0]
        metrics = {
            "total_signals": len(signals),
            "total_trades": len(trades),
            "risk_blocked": len(risk_events),
            "final_realized_pnl": final_state.realized_pnl,
            "signal_frequency": signal_frequency(signals),
            "average_confidence": average_confidence(signals),
            "long_short_distribution": long_short_distribution(signals),
            "total_return": final_state.realized_pnl,
        }

        return BacktestResult(
            signals=signals,
            trades=trades,
            equity_curve=equity_curve,
            risk_events=risk_events,
            evaluation_metrics=metrics,
        )
