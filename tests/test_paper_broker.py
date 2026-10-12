import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from src.contracts.signal import Signal, SignalDirection
from src.contracts.order import Order, OrderStatus, OrderSide
from src.brokers.paper_broker import PaperBroker

_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

def sig(direction: SignalDirection) -> Signal:
    return Signal(symbol="GLD", direction=direction, confidence=0.5,
                  strategy_id="test", generated_at=_ts)


def test_long_order_filled():
    broker = PaperBroker()
    order = broker.submit_order(sig(SignalDirection.LONG), 180.0)
    assert order.status == OrderStatus.FILLED
    assert order.filled_price == 180.0
    assert order.side == OrderSide.BUY


def test_short_order_filled():
    broker = PaperBroker()
    order = broker.submit_order(sig(SignalDirection.SHORT), 175.0)
    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.SELL


def test_flat_closes_position():
    broker = PaperBroker()
    broker.submit_order(sig(SignalDirection.LONG), 180.0)
    order = broker.submit_order(sig(SignalDirection.FLAT), 185.0)
    assert order.status == OrderStatus.FILLED
    state = broker.get_account_state()
    assert abs(state["realized_pnl"] - 5.0) < 1e-9
    assert not state["open_position"]


def test_repeated_signal_rejected():
    broker = PaperBroker()
    broker.submit_order(sig(SignalDirection.LONG), 180.0)
    order = broker.submit_order(sig(SignalDirection.LONG), 182.0)
    assert order.status == OrderStatus.REJECTED


def test_order_has_id():
    broker = PaperBroker()
    order = broker.submit_order(sig(SignalDirection.LONG), 180.0)
    assert order.order_id is not None and len(order.order_id) > 0


def test_get_positions_after_long():
    broker = PaperBroker()
    broker.submit_order(sig(SignalDirection.LONG), 180.0)
    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "GLD"


def test_get_positions_flat():
    broker = PaperBroker()
    assert broker.get_positions() == []


def test_account_state_schema():
    broker = PaperBroker()
    state = broker.get_account_state()
    assert "realized_pnl" in state
    assert "unrealized_pnl" in state
    assert "fill_count" in state
    assert "open_position" in state


def test_deterministic():
    def run():
        b = PaperBroker()
        b.submit_order(sig(SignalDirection.LONG), 100.0)
        b.submit_order(sig(SignalDirection.FLAT), 110.0)
        return b.get_account_state()["realized_pnl"]
    assert run() == run()


def test_returns_order_type():
    broker = PaperBroker()
    order = broker.submit_order(sig(SignalDirection.LONG), 180.0)
    assert isinstance(order, Order)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
