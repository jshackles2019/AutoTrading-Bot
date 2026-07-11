"""Unit tests for risk_manager.py."""

from src.risk_manager import evaluate


def test_no_buy_signal():
    account = {"equity": 100000, "buying_power": 50000}
    signal = {"symbol": "AAPL", "action": "NONE"}
    config = {"max_risk_pct": 0.01}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "No BUY signal"
    assert result["shares"] == 0


def test_missing_prices():
    account = {"equity": 100000, "buying_power": 50000}
    signal = {"symbol": "AAPL", "action": "BUY"}
    config = {"max_risk_pct": 0.01}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "Missing entry or stop level"


def test_negative_risk():
    account = {"equity": 100000, "buying_power": 50000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 100.0, "stop_level": 101.0}
    config = {"max_risk_pct": 0.01}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "Stop loss must be below entry price"


def test_minimum_shares_not_met():
    account = {"equity": 1000, "buying_power": 1000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 100.0, "stop_level": 95.0}
    config = {"max_risk_pct": 0.001, "min_shares": 1}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "Trade size below minimum shares"


def test_insufficient_buying_power():
    account = {"equity": 100000, "buying_power": 100}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 150.0, "stop_level": 145.0}
    config = {"max_risk_pct": 0.01, "min_shares": 1}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "Insufficient buying power"
    assert result["shares"] == 0


def test_max_trades_per_day_reached():
    account = {"equity": 100000, "buying_power": 50000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 150.0, "stop_level": 145.0}
    config = {"max_risk_pct": 0.01, "max_trades_per_day": 1, "current_trades_today": 1}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert "Max trades per day reached" in result["reason"]


def test_open_risk_limit_exceeded():
    account = {"equity": 100000, "buying_power": 100000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 150.0, "stop_level": 145.0}
    config = {"max_risk_pct": 0.01, "max_open_risk_pct": 0.01, "current_open_risk": 980.0}

    result = evaluate(account, signal, config)

    assert result["allowed"] is False
    assert result["reason"] == "Open risk would exceed allowed maximum"


def test_allowed_trade():
    account = {"equity": 100000, "buying_power": 100000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 150.0, "stop_level": 145.0, "target_level": 160.0}
    config = {"max_risk_pct": 0.01, "max_position_pct": 0.05}

    result = evaluate(account, signal, config)

    assert result["allowed"] is True
    assert result["shares"] > 0
    assert result["reason"] == "Allowed"
    assert result["risk_per_share"] == 5.0
    assert result["max_risk_dollars"] == 1000.0
    assert result["risk_dollars"] == round(result["shares"] * 5.0, 2)


def test_position_notional_cap():
    account = {"equity": 100000, "buying_power": 50000}
    signal = {"symbol": "AAPL", "action": "BUY", "entry_level": 200.0, "stop_level": 190.0}
    config = {"max_risk_pct": 0.01, "max_position_pct": 0.01, "min_shares": 1}

    result = evaluate(account, signal, config)
    assert result["allowed"] is True
    assert result["shares"] <= 10
