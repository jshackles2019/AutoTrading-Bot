"""Tests for startup preflight gate behavior."""

from src.main import TradingSession


def test_preflight_blocks_on_non_active_status():
    session = TradingSession(
        {"symbols": ["AAPL"], "risk": {}, "automation": {"preflight": {"enabled": True}}},
        dry_run=True,
    )
    session.entry_lockout = False
    session.entry_lockout_reason = None
    session.halt_reason = None

    ok = session._run_preflight_gate({"status": "Blocked", "buying_power": 1000.0, "equity": 100000.0})

    assert ok is False


def test_preflight_blocks_on_non_positive_buying_power():
    session = TradingSession(
        {"symbols": ["AAPL"], "risk": {}, "automation": {"preflight": {"enabled": True}}},
        dry_run=True,
    )
    session.entry_lockout = False
    session.entry_lockout_reason = None
    session.halt_reason = None

    ok = session._run_preflight_gate({"status": "Active", "buying_power": 0.0, "equity": 100000.0})

    assert ok is False


def test_preflight_blocks_when_entry_lockout_already_active():
    session = TradingSession(
        {"symbols": ["AAPL"], "risk": {}, "automation": {"preflight": {"enabled": True}}},
        dry_run=True,
    )
    session.entry_lockout = True
    session.entry_lockout_reason = "prior mismatch"

    ok = session._run_preflight_gate({"status": "Active", "buying_power": 1000.0, "equity": 100000.0})

    assert ok is False


def test_preflight_allows_when_checks_pass():
    session = TradingSession(
        {"symbols": ["AAPL"], "risk": {}, "automation": {"preflight": {"enabled": True}}},
        dry_run=True,
    )
    session.entry_lockout = False
    session.entry_lockout_reason = None
    session.halt_reason = None

    ok = session._run_preflight_gate({"status": "Active", "buying_power": 1000.0, "equity": 100000.0})

    assert ok is True
