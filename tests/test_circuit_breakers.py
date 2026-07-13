"""Tests for circuit-breaker behavior in trading session."""

from src.main import TradingSession


def test_forced_halt_test_hook_triggers_immediately():
    config = {
        "symbols": ["AAPL"],
        "risk": {},
        "test_hooks": {
            "force_halt_after_loops": 0,
            "force_halt_reason": "pytest forced halt",
        },
    }

    session = TradingSession(config, dry_run=True, max_loops=1, bypass_market_hours=True)

    triggered = session._check_test_hook_halt(loop_count=0, account_equity=100000.0)

    assert triggered is True
    assert session.halt_reason == "pytest forced halt"


def test_daily_drawdown_breaker_triggers_halt():
    config = {
        "symbols": ["AAPL"],
        "risk": {
            "max_daily_drawdown_pct": 0.02,
            "max_consecutive_losses": 3,
            "max_open_positions": 5,
            "symbol_cooldown_minutes": 30,
        },
    }

    session = TradingSession(config, dry_run=True, max_loops=1, bypass_market_hours=True)
    session.session_start_equity = 100000.0

    should_halt = session._check_circuit_breakers({"equity": 97000.0})

    assert should_halt is True
    assert session.halt_reason is not None
    assert "Daily drawdown limit exceeded" in session.halt_reason
