"""Tests for strict trading schedule gate behavior."""

from datetime import datetime

from src.main import TradingSession
from src import utils


def _market_dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return utils.MARKET_TZ.localize(datetime(year, month, day, hour, minute))


def test_schedule_gate_disabled_allows_any_time():
    session = TradingSession(
        {
            "symbols": ["AAPL"],
            "risk": {},
            "automation": {
                "trading_window": {
                    "enabled": False,
                    "start": "09:30",
                    "end": "16:00",
                    "weekdays": [0, 1, 2, 3, 4],
                }
            },
        },
        dry_run=True,
    )

    assert session._within_schedule_window(_market_dt(2026, 7, 13, 3, 0)) is True


def test_schedule_gate_allows_in_window_weekday():
    session = TradingSession(
        {
            "symbols": ["AAPL"],
            "risk": {},
            "automation": {
                "trading_window": {
                    "enabled": True,
                    "start": "09:30",
                    "end": "16:00",
                    "weekdays": [0, 1, 2, 3, 4],
                }
            },
        },
        dry_run=True,
    )

    # Monday 10:00 ET
    assert session._within_schedule_window(_market_dt(2026, 7, 13, 10, 0)) is True


def test_schedule_gate_blocks_outside_window_or_weekday():
    session = TradingSession(
        {
            "symbols": ["AAPL"],
            "risk": {},
            "automation": {
                "trading_window": {
                    "enabled": True,
                    "start": "09:30",
                    "end": "16:00",
                    "weekdays": [0, 1, 2, 3, 4],
                }
            },
        },
        dry_run=True,
    )

    # Monday 08:45 ET
    assert session._within_schedule_window(_market_dt(2026, 7, 13, 8, 45)) is False
    # Sunday 10:00 ET
    assert session._within_schedule_window(_market_dt(2026, 7, 12, 10, 0)) is False
