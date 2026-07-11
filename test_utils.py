#!/usr/bin/env python3
"""Test script for utils.py

Tests configuration loading, time utilities, market hours detection, and validation.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pytz

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import utils


def test_config_loading():
    """Test: Load configuration from YAML."""
    print("\n" + "="*60)
    print("TEST 1: Load Configuration")
    print("="*60)
    
    try:
        config = utils.load_config()
        print(f"✓ Config loaded successfully")
        print(f"  Symbols: {config.get('symbols')}")
        print(f"  Timeframe: {config.get('timeframe')}")
        print(f"  Max trades/day: {config.get('risk', {}).get('max_trades_per_day')}")
        assert config is not None, "Config should not be None"
        assert "symbols" in config, "Config should have symbols"
        print("✓ Test passed")
        return True
    except Exception as e:
        print(f"✗ Failed to load config: {e}")
        return False


def test_now_utc():
    """Test: Get current UTC time."""
    print("\n" + "="*60)
    print("TEST 2: Current UTC Time")
    print("="*60)
    
    now = utils.now_utc()
    print(f"UTC Time: {now}")
    print(f"Timezone: {now.tzinfo}")
    
    assert now is not None, "Should return datetime"
    assert now.tzinfo is not None, "Should be timezone-aware"
    print("✓ Test passed")
    return True


def test_now_market():
    """Test: Get current market timezone time."""
    print("\n" + "="*60)
    print("TEST 3: Current Market Time (EST/EDT)")
    print("="*60)
    
    now = utils.now_market()
    print(f"Market Time: {now}")
    print(f"Timezone: {now.tzinfo}")
    
    assert now is not None, "Should return datetime"
    assert now.tzinfo is not None, "Should be timezone-aware"
    print("✓ Test passed")
    return True


def test_now_iso():
    """Test: Get current time as ISO string."""
    print("\n" + "="*60)
    print("TEST 4: Current Time ISO Format")
    print("="*60)
    
    iso = utils.now_iso()
    print(f"ISO String: {iso}")
    
    assert isinstance(iso, str), "Should return string"
    assert "T" in iso, "Should be ISO format"
    print("✓ Test passed")
    return True


def test_market_hours():
    """Test: Check if market is open at specific times."""
    print("\n" + "="*60)
    print("TEST 5: Market Hours Detection")
    print("="*60)
    
    tz = pytz.timezone("America/New_York")
    
    # Monday 10:00 AM (should be open)
    monday_10am = tz.localize(datetime(2026, 7, 13, 10, 0, 0))  # Monday
    is_open_1 = utils.is_market_open(monday_10am)
    print(f"Monday 10:00 AM: Open = {is_open_1}")
    assert is_open_1 is True, "Should be open on Monday at 10 AM"
    
    # Monday 9:00 AM (before open)
    monday_9am = tz.localize(datetime(2026, 7, 13, 9, 0, 0))
    is_open_2 = utils.is_market_open(monday_9am)
    print(f"Monday 9:00 AM: Open = {is_open_2}")
    assert is_open_2 is False, "Should be closed before market open"
    
    # Sunday (weekend)
    sunday = tz.localize(datetime(2026, 7, 12, 10, 0, 0))  # Sunday
    is_open_3 = utils.is_market_open(sunday)
    print(f"Sunday 10:00 AM: Open = {is_open_3}")
    assert is_open_3 is False, "Should be closed on Sunday"
    
    print("✓ Test passed")
    return True


def test_market_hours_remaining():
    """Test: Calculate hours remaining until market close."""
    print("\n" + "="*60)
    print("TEST 6: Market Hours Remaining")
    print("="*60)
    
    tz = pytz.timezone("America/New_York")
    
    # Monday 3:00 PM (1 hour before close at 4:00 PM)
    monday_3pm = tz.localize(datetime(2026, 7, 13, 15, 0, 0))
    remaining = utils.market_hours_remaining(monday_3pm)
    print(f"Monday 3:00 PM: Hours remaining = {remaining}")
    assert remaining.total_seconds() > 0, "Should have time remaining"
    assert remaining.total_seconds() < 3600 * 2, "Should be less than 2 hours"
    
    # After hours (should return 0)
    monday_5pm = tz.localize(datetime(2026, 7, 13, 17, 0, 0))
    remaining_2 = utils.market_hours_remaining(monday_5pm)
    print(f"Monday 5:00 PM: Hours remaining = {remaining_2}")
    assert remaining_2.total_seconds() == 0, "Should return 0 after market close"
    
    print("✓ Test passed")
    return True


def test_next_market_open():
    """Test: Calculate next market open."""
    print("\n" + "="*60)
    print("TEST 7: Next Market Open")
    print("="*60)
    
    tz = pytz.timezone("America/New_York")
    
    # From Monday 3:00 PM (should be next day at 9:30 AM)
    monday_3pm = tz.localize(datetime(2026, 7, 13, 15, 0, 0))
    next_open = utils.next_market_open(monday_3pm)
    print(f"From Monday 3:00 PM: Next open = {next_open}")
    assert next_open.weekday() == 0, "Should be Monday (next trading day)"
    assert next_open.time().hour == 9, "Should be at 9 AM"
    assert next_open.time().minute == 30, "Should be at 30 minutes"
    
    # From Friday 3:00 PM (should skip weekend, open Monday)
    friday_3pm = tz.localize(datetime(2026, 7, 10, 15, 0, 0))
    next_open_2 = utils.next_market_open(friday_3pm)
    print(f"From Friday 3:00 PM: Next open = {next_open_2}")
    assert next_open_2.weekday() == 0, "Should be Monday after weekend"
    
    print("✓ Test passed")
    return True


def test_validate_symbol():
    """Test: Symbol validation."""
    print("\n" + "="*60)
    print("TEST 8: Symbol Validation")
    print("="*60)
    
    # Valid symbols
    assert utils.validate_symbol("AAPL") is True, "AAPL should be valid"
    assert utils.validate_symbol("SPY") is True, "SPY should be valid"
    assert utils.validate_symbol("X") is True, "Single letter should be valid"
    
    # Invalid symbols
    assert utils.validate_symbol("AAPL1") is False, "Should not have numbers"
    assert utils.validate_symbol("") is False, "Empty should be invalid"
    assert utils.validate_symbol("TOOLONGNAME") is False, "Too long should be invalid"
    assert utils.validate_symbol("123") is False, "Numbers only should be invalid"
    
    print("✓ Valid: AAPL, SPY, X")
    print("✓ Invalid: AAPL1, empty, TOOLONGNAME, 123")
    print("✓ Test passed")
    return True


def test_validate_symbols():
    """Test: Multiple symbols validation."""
    print("\n" + "="*60)
    print("TEST 9: Multiple Symbols Validation")
    print("="*60)
    
    # Valid list
    assert utils.validate_symbols(["AAPL", "SPY", "MSFT"]) is True
    print("✓ Valid list: AAPL, SPY, MSFT")
    
    # Invalid list (contains bad symbol)
    assert utils.validate_symbols(["AAPL", "INVALID123"]) is False
    print("✓ Invalid list detected: AAPL, INVALID123")
    
    # Empty list
    assert utils.validate_symbols([]) is False
    print("✓ Empty list rejected")
    
    print("✓ Test passed")
    return True


def test_format_price():
    """Test: Price formatting."""
    print("\n" + "="*60)
    print("TEST 10: Price Formatting")
    print("="*60)
    
    price1 = utils.format_price(150.25)
    print(f"150.25 → {price1}")
    assert price1 == "$150.25", "Should format as currency"
    
    price2 = utils.format_price(1000.5)
    print(f"1000.5 → {price2}")
    assert "$1,000.50" in price2, "Should add comma separator"
    
    print("✓ Test passed")
    return True


def test_format_pnl():
    """Test: P&L formatting."""
    print("\n" + "="*60)
    print("TEST 11: P&L Formatting")
    print("="*60)
    
    pnl1 = utils.format_pnl(100.50, 1.25)
    print(f"PnL +100.50 +1.25%: {pnl1}")
    assert "+" in pnl1, "Should show positive sign"
    assert "$100.50" in pnl1, "Should show amount"
    
    pnl2 = utils.format_pnl(-50.00, -0.75)
    print(f"PnL -50.00 -0.75%: {pnl2}")
    assert "-" in pnl2, "Should show negative"
    
    print("✓ Test passed")
    return True


def test_format_shares():
    """Test: Share quantity formatting."""
    print("\n" + "="*60)
    print("TEST 12: Shares Formatting")
    print("="*60)
    
    shares1 = utils.format_shares(100)
    print(f"100 shares: {shares1}")
    assert shares1 == "100", "Should format correctly"
    
    shares2 = utils.format_shares(1000000)
    print(f"1,000,000 shares: {shares2}")
    assert "," in shares2, "Should add commas"
    
    print("✓ Test passed")
    return True


def test_seconds_to_hms():
    """Test: Seconds to HH:MM:SS conversion."""
    print("\n" + "="*60)
    print("TEST 13: Seconds to HH:MM:SS")
    print("="*60)
    
    hms1 = utils.seconds_to_hms(3661)  # 1 hour, 1 minute, 1 second
    print(f"3661 seconds: {hms1}")
    assert hms1 == "01:01:01", "Should convert correctly"
    
    hms2 = utils.seconds_to_hms(86400)  # 24 hours
    print(f"86400 seconds: {hms2}")
    assert hms2 == "24:00:00", "Should handle full day"
    
    print("✓ Test passed")
    return True


def test_clamp():
    """Test: Clamp value between min and max."""
    print("\n" + "="*60)
    print("TEST 14: Clamp Function")
    print("="*60)
    
    assert utils.clamp(5, 0, 10) == 5, "Should return unchanged value"
    assert utils.clamp(-5, 0, 10) == 0, "Should clamp to min"
    assert utils.clamp(15, 0, 10) == 10, "Should clamp to max"
    
    print("✓ Clamp tests passed")
    print("✓ Test passed")
    return True


def test_safe_divide():
    """Test: Safe division with zero handling."""
    print("\n" + "="*60)
    print("TEST 15: Safe Divide Function")
    print("="*60)
    
    result1 = utils.safe_divide(10, 2)
    print(f"10 / 2 = {result1}")
    assert result1 == 5.0, "Should divide correctly"
    
    result2 = utils.safe_divide(10, 0)
    print(f"10 / 0 = {result2} (default)")
    assert result2 == 0.0, "Should return default on division by zero"
    
    result3 = utils.safe_divide(10, 0, default=99.0)
    print(f"10 / 0 = {result3} (custom default)")
    assert result3 == 99.0, "Should return custom default"
    
    print("✓ Test passed")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("UTILS TEST SUITE")
    print("="*60)
    
    tests = [
        ("Load Configuration", test_config_loading),
        ("Current UTC Time", test_now_utc),
        ("Current Market Time", test_now_market),
        ("ISO Format Time", test_now_iso),
        ("Market Hours Detection", test_market_hours),
        ("Market Hours Remaining", test_market_hours_remaining),
        ("Next Market Open", test_next_market_open),
        ("Symbol Validation", test_validate_symbol),
        ("Multiple Symbols", test_validate_symbols),
        ("Price Formatting", test_format_price),
        ("P&L Formatting", test_format_pnl),
        ("Shares Formatting", test_format_shares),
        ("Seconds to HMS", test_seconds_to_hms),
        ("Clamp Function", test_clamp),
        ("Safe Divide", test_safe_divide),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except AssertionError as e:
            print(f"✗ Test failed: {e}")
            results[name] = False
        except Exception as e:
            print(f"✗ Test error: {e}")
            results[name] = False
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    for name, result in results.items():
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
    
    print("\n" + "="*60)
    if passed == total:
        print("✓ ALL TESTS PASSED")
    else:
        print(f"✗ {total - passed} TEST(S) FAILED")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
