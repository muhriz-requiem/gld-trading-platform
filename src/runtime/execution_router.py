from src.runtime.mode import RuntimeMode
from src.runtime.config import RuntimeConfig, load_broker_config


class ExecutionRouter:
    """
    Selects the correct execution backend based on RuntimeConfig.
    Never modifies any backend. Routing logic only.
    Subsystems receive no knowledge of the active runtime mode.
    """

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config

    def get_backend(self):
        mode = self._config.mode

        if mode == RuntimeMode.BACKTEST:
            from src.orchestration.backtest_runner import BacktestRunner
            return BacktestRunner()

        if mode == RuntimeMode.PAPER:
            from src.brokers.alpaca_paper_broker import AlpacaPaperBroker

            broker_config = load_broker_config()
            return AlpacaPaperBroker(broker_config)

        if mode == RuntimeMode.LIVE:
            self._enforce_live_gate()

            from src.brokers.alpaca_paper_broker import AlpacaPaperBroker

            broker_config = load_broker_config()
            return AlpacaPaperBroker(broker_config)

        raise RuntimeError(f"Unknown RuntimeMode: {mode}")

    def _enforce_live_gate(self) -> None:
        """
        Hard safety gate for LIVE mode.
        """

        if self._config.strict_mode:
            raise RuntimeError(
                "LIVE mode blocked: STRICT_MODE=true"
            )

        if not self._config.allow_live_trading:
            raise RuntimeError(
                "LIVE mode blocked: ALLOW_LIVE_TRADING=false"
            )
