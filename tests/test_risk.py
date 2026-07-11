"""Basic pytest stub for risk manager."""
from src.risk_manager import evaluate


def test_risk_stub():
    res = evaluate({"equity": 100000}, {"symbol": "AAPL", "action": "NONE"}, {"max_risk_pct": 0.01})
    assert isinstance(res, dict)
    assert "allowed" in res
