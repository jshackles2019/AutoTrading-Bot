"""Basic pytest stub for strategy."""
from src.strategy_breakout import evaluate


def test_evaluate_no_bars():
    signal = evaluate([], "AAPL")
    assert isinstance(signal, dict)
    assert signal.get("action") in ("BUY", "NONE")
