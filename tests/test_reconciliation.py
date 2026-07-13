"""Tests for startup position reconciliation and safe-mode lockout."""

import json

from src.main import TradingSession


def test_startup_reconciliation_mismatch_enables_entry_lockout(monkeypatch):
    from src import main as main_module

    monkeypatch.setattr(
        main_module.alpaca_client,
        "get_open_positions",
        lambda: [{"symbol": "AAPL", "qty": 1}],
    )

    session = TradingSession({"symbols": ["AAPL"], "risk": {}}, dry_run=True)
    session.active_trades = {}

    session._perform_startup_reconciliation()

    assert session.entry_lockout is True
    assert session.entry_lockout_reason is not None
    assert "mismatch" in session.entry_lockout_reason.lower()


def test_startup_reconciliation_match_allows_entries(monkeypatch):
    from src import main as main_module

    monkeypatch.setattr(
        main_module.alpaca_client,
        "get_open_positions",
        lambda: [{"symbol": "AAPL", "qty": 1}],
    )

    session = TradingSession({"symbols": ["AAPL"], "risk": {}}, dry_run=True)
    session.active_trades = {
        "AAPL": {
            "order_id": "dryrun-1",
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "target": 105.0,
            "shares": 1,
            "risk_dollars": 1.0,
        }
    }
    session.entry_lockout = False
    session.entry_lockout_reason = None

    session._perform_startup_reconciliation()

    assert session.entry_lockout is False


def test_runtime_status_marks_safe_mode_when_running_and_locked(tmp_path):
    from src import main as main_module

    runtime_file = tmp_path / "runtime_status.json"
    original_path = main_module.RUNTIME_STATUS_PATH
    original_data_dir = main_module.DATA_UI_DIR
    try:
        main_module.RUNTIME_STATUS_PATH = runtime_file
        main_module.DATA_UI_DIR = tmp_path
        session = TradingSession({"symbols": ["AAPL"], "risk": {}}, dry_run=True)
        session.entry_lockout = True
        session.entry_lockout_reason = "test lockout"

        session._write_runtime_status("running", "Trading loop active")

        payload = json.loads(runtime_file.read_text(encoding="utf-8"))
        assert payload.get("status") == "safe_mode_lockout"
        assert payload.get("entry_lockout") is True
        assert payload.get("entry_lockout_reason") == "test lockout"
    finally:
        main_module.RUNTIME_STATUS_PATH = original_path
        main_module.DATA_UI_DIR = original_data_dir
