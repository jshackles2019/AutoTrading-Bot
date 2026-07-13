"""Tests for circuit-breaker behavior in trading session."""

import json
from pathlib import Path

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


def test_restore_runtime_context_recovers_losses_and_cooldowns(tmp_path):
    runtime_file = tmp_path / "runtime_status.json"
    runtime_file.write_text(
        json.dumps(
            {
                "consecutive_losses": 2,
                "session_start_equity": 101000.0,
                "symbol_cooldowns": {"AAPL": 1234567890.0, "msft": 2234567890.0},
            }
        ),
        encoding="utf-8",
    )

    from src import main as main_module

    original_path = main_module.RUNTIME_STATUS_PATH
    try:
        main_module.RUNTIME_STATUS_PATH = runtime_file
        session = TradingSession({"symbols": ["AAPL"], "risk": {}}, dry_run=True)
    finally:
        main_module.RUNTIME_STATUS_PATH = original_path

    assert session.consecutive_losses == 2
    assert session.session_start_equity == 101000.0
    assert session.symbol_cooldowns.get("AAPL") == 1234567890.0
    assert session.symbol_cooldowns.get("MSFT") == 2234567890.0


def test_reset_runtime_context_clears_state_and_optionally_cooldowns(tmp_path):
    runtime_file = tmp_path / "runtime_status.json"

    from src import main as main_module

    original_path = main_module.RUNTIME_STATUS_PATH
    try:
        main_module.RUNTIME_STATUS_PATH = runtime_file
        session = TradingSession({"symbols": ["AAPL"], "risk": {}}, dry_run=True)
        session.consecutive_losses = 3
        session.symbol_cooldowns = {"AAPL": 123.0}

        session._reset_runtime_context(clear_cooldowns=False)
        assert session.consecutive_losses == 0
        assert session.symbol_cooldowns == {"AAPL": 123.0}

        session._reset_runtime_context(clear_cooldowns=True)
        assert session.symbol_cooldowns == {}

        saved = json.loads(runtime_file.read_text(encoding="utf-8"))
        assert saved.get("status") == "reset"
    finally:
        main_module.RUNTIME_STATUS_PATH = original_path
