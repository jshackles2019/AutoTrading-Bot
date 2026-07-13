"""Tests for startup preflight gate behavior."""

from datetime import timedelta

from src.main import TradingSession
from src import main as main_module


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


def test_preflight_blocks_on_stale_market_data_when_market_open(monkeypatch):
    session = TradingSession(
        {
            "symbols": ["AAPL"],
            "timeframe": "5Min",
            "risk": {},
            "automation": {
                "preflight": {
                    "enabled": True,
                    "max_market_data_age_minutes": 5,
                    "symbols_to_check": 1,
                }
            },
        },
        dry_run=True,
    )
    session.entry_lockout = False
    session.entry_lockout_reason = None
    session.halt_reason = None

    now_market = main_module.utils.now_market()
    stale_ts = now_market - timedelta(minutes=15)

    monkeypatch.setattr(main_module.utils, "is_market_open", lambda *args, **kwargs: True)
    monkeypatch.setattr(main_module.utils, "now_market", lambda *args, **kwargs: now_market)
    monkeypatch.setattr(
        main_module.alpaca_client,
        "get_bars",
        lambda symbol, timeframe, lookback=1: [{"timestamp": stale_ts}],
    )

    ok = session._run_preflight_gate({"status": "Active", "buying_power": 1000.0, "equity": 100000.0})

    assert ok is False


def test_preflight_skips_stale_data_check_when_market_closed(monkeypatch):
    session = TradingSession(
        {
            "symbols": ["AAPL"],
            "timeframe": "5Min",
            "risk": {},
            "automation": {
                "preflight": {
                    "enabled": True,
                    "max_market_data_age_minutes": 5,
                    "symbols_to_check": 1,
                }
            },
        },
        dry_run=True,
    )
    session.entry_lockout = False
    session.entry_lockout_reason = None
    session.halt_reason = None

    monkeypatch.setattr(main_module.utils, "is_market_open", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        main_module.alpaca_client,
        "get_bars",
        lambda symbol, timeframe, lookback=1: [],
    )

    ok = session._run_preflight_gate({"status": "Active", "buying_power": 1000.0, "equity": 100000.0})

    assert ok is True
