"""Unit tests for executor.py."""

from src.executor import build_order_payload, submit_order, close_position


class DummyClient:
    def __init__(self):
        self.last_order = None
        self.last_bracket = None
        self.last_close = None

    def submit_order(self, order_params):
        self.last_order = order_params
        return {"id": "dummy-order", "symbol": order_params.get("symbol"), "qty": order_params.get("qty"), "side": order_params.get("side"), "status": "submitted"}

    def submit_bracket_order(self, order_params):
        self.last_bracket = order_params
        return {"id": "dummy-bracket", "symbol": order_params.get("symbol"), "qty": order_params.get("qty"), "side": order_params.get("side"), "status": "submitted"}

    def close_position(self, symbol, qty=None):
        self.last_close = {"symbol": symbol, "qty": qty}
        return {"id": "dummy-close", "symbol": symbol, "qty": qty or 0, "status": "closed"}


class DummyLogger:
    def __init__(self):
        self.orders = []
        self.errors = []

    def log_order(self, order):
        self.orders.append(order)

    def log_error(self, message, exc_info=None):
        self.errors.append((message, exc_info))


def test_build_order_payload_defaults():
    payload = build_order_payload("AAPL", 10)
    assert payload["symbol"] == "AAPL"
    assert payload["qty"] == 10
    assert payload["side"] == "buy"
    assert payload["type"] == "market"
    assert payload["time_in_force"] == "day"


def test_build_order_payload_limit():
    payload = build_order_payload("SPY", 5, side="sell", order_type="limit", limit_price=450.0)
    assert payload["type"] == "limit"
    assert payload["limit_price"] == 450.0


def test_build_order_payload_invalid_side():
    try:
        build_order_payload("AAPL", 1, side="hold")
        assert False, "Expected ValueError for invalid side"
    except ValueError as exc:
        assert "side must be 'buy' or 'sell'" in str(exc)


def test_submit_order_forwards_to_client_and_logs():
    client = DummyClient()
    logger = DummyLogger()
    payload = build_order_payload("AAPL", 3)

    order = submit_order(payload, client=client, logger=logger)

    assert client.last_order == payload
    assert order["id"] == "dummy-order"
    assert logger.orders[0] == order


def test_submit_order_with_bracket_support():
    client = DummyClient()
    logger = DummyLogger()
    payload = build_order_payload("AAPL", 3, stop_loss=145.0, take_profit=155.0)

    order = submit_order(payload, client=client, logger=logger, use_bracket=True)

    assert client.last_bracket == payload
    assert order["id"] == "dummy-bracket"
    assert logger.orders[0] == order


def test_submit_order_with_bracket_fallback_when_not_supported():
    class NoBracketClient:
        def __init__(self):
            self.last_order = None

        def submit_order(self, order_params):
            self.last_order = order_params
            return {"id": "dummy-order", "symbol": order_params.get("symbol"), "qty": order_params.get("qty"), "side": order_params.get("side"), "status": "submitted"}

    client = NoBracketClient()
    logger = DummyLogger()
    payload = build_order_payload("AAPL", 3, stop_loss=145.0, take_profit=155.0)

    order = submit_order(payload, client=client, logger=logger, use_bracket=True)

    assert client.last_order == payload
    assert order["id"] == "dummy-order"
    assert logger.errors, "Expected error logged when bracket unsupported"


def test_close_position_uses_client_close_position_and_logs():
    client = DummyClient()
    logger = DummyLogger()

    order = close_position("AAPL", qty=5, client=client, logger=logger)

    assert client.last_close == {"symbol": "AAPL", "qty": 5}
    assert order["id"] == "dummy-close"
    assert logger.orders[0] == order
