#!/usr/bin/env python3
"""Test script for risk_manager.py

Tests position sizing, risk limits, and trade approval logic.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from risk_manager import evaluate


def test_no_signal():
    """Test: Trade rejected when no BUY signal."""
    print("\n" + "="*60)
    print("TEST 1: No Signal")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {"action": "NONE"}
    config = {}
    
    result = evaluate(account, signal, config)
    
    print(f"Result: {result}")
    assert result["allowed"] is False, "Should reject non-BUY signal"
    assert "No BUY signal" in result["reason"], "Should mention signal"
    print("✓ Test passed")
    return True


def test_basic_buy_signal():
    """Test: BUY signal accepted with basic position sizing."""
    print("\n" + "="*60)
    print("TEST 2: Basic BUY Signal")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 149.00,
        "target_level": 155.00,
    }
    config = {"max_risk_pct": 0.01}
    
    result = evaluate(account, signal, config)
    
    print(f"Entry: {signal['entry_level']}")
    print(f"Stop: {signal['stop_level']}")
    print(f"Risk per share: {result.get('risk_per_share')}")
    print(f"Max risk: ${result.get('max_risk_dollars')}")
    print(f"Shares: {result.get('shares')}")
    print(f"Allowed: {result['allowed']}")
    
    assert result["allowed"] is True, "Should allow valid BUY signal"
    assert result["shares"] > 0, "Should calculate positive shares"
    print("✓ Test passed")
    return True


def test_max_daily_trades():
    """Test: Trade rejected when max daily trades reached."""
    print("\n" + "="*60)
    print("TEST 3: Max Daily Trades Limit")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 149.00,
    }
    config = {
        "max_trades_per_day": 3,
        "current_trades_today": 3,
    }
    
    result = evaluate(account, signal, config)
    
    print(f"Current trades: 3")
    print(f"Max trades: 3")
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    
    assert result["allowed"] is False, "Should reject when max trades reached"
    assert "Max trades" in result["reason"], "Should mention max trades"
    print("✓ Test passed")
    return True


def test_insufficient_buying_power():
    """Test: Trade rejected with insufficient buying power."""
    print("\n" + "="*60)
    print("TEST 4: Insufficient Buying Power")
    print("="*60)
    
    account = {"equity": 100000, "cash": 100}  # Very low cash
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 149.00,
    }
    config = {"max_risk_pct": 0.01}
    
    result = evaluate(account, signal, config)
    
    print(f"Equity: $100,000")
    print(f"Cash: $100")
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    
    assert result["allowed"] is False, "Should reject insufficient buying power"
    assert "buying power" in result["reason"].lower(), "Should mention buying power"
    print("✓ Test passed")
    return True


def test_max_position_size():
    """Test: Position size capped at max position notional."""
    print("\n" + "="*60)
    print("TEST 5: Max Position Size Limit")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 100.00,
        "stop_level": 95.00,
    }
    config = {
        "max_risk_pct": 0.05,  # Would normally allow many shares
        "max_position_pct": 0.05,  # But cap position to 5% of equity
    }
    
    result = evaluate(account, signal, config)
    
    print(f"Equity: $100,000")
    print(f"Max risk %: 5%")
    print(f"Max position %: 5%")
    print(f"Entry price: $100")
    print(f"Shares allowed: {result.get('shares')}")
    print(f"Position notional: ${result.get('shares') * signal['entry_level']}")
    
    assert result["allowed"] is True, "Should allow trade with size limits"
    max_notional = 100000 * 0.05
    actual_notional = result["shares"] * signal["entry_level"]
    assert actual_notional <= max_notional, "Position should not exceed max notional"
    print("✓ Test passed")
    return True


def test_max_open_risk():
    """Test: Trade rejected when total open risk would exceed limit."""
    print("\n" + "="*60)
    print("TEST 6: Max Open Risk Limit")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 149.00,
    }
    config = {
        "max_risk_pct": 0.01,
        "max_open_risk_pct": 0.02,
        "current_open_risk": 1500.00,  # Already have $1500 at risk
    }
    
    result = evaluate(account, signal, config)
    
    print(f"Equity: $100,000")
    print(f"Max open risk %: 2% ($2,000)")
    print(f"Current open risk: $1,500")
    print(f"This trade risk: ${result.get('risk_dollars', 'N/A')}")
    print(f"Allowed: {result['allowed']}")
    
    if not result["allowed"]:
        assert "Open risk" in result["reason"], "Should mention open risk"
    print("✓ Test passed")
    return True


def test_invalid_stop_loss():
    """Test: Trade rejected when stop is not below entry."""
    print("\n" + "="*60)
    print("TEST 7: Invalid Stop Loss (Not Below Entry)")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 151.00,  # Stop ABOVE entry (invalid)
    }
    config = {}
    
    result = evaluate(account, signal, config)
    
    print(f"Entry: $150")
    print(f"Stop: $151")
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    
    assert result["allowed"] is False, "Should reject invalid stop"
    assert "Stop loss" in result["reason"], "Should mention stop loss"
    print("✓ Test passed")
    return True


def test_missing_prices():
    """Test: Trade rejected with missing entry/stop prices."""
    print("\n" + "="*60)
    print("TEST 8: Missing Entry or Stop Prices")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        # Missing stop_level
    }
    config = {}
    
    result = evaluate(account, signal, config)
    
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    
    assert result["allowed"] is False, "Should reject missing prices"
    assert "Missing" in result["reason"], "Should mention missing field"
    print("✓ Test passed")
    return True


def test_detailed_metrics():
    """Test: Verify detailed metrics returned."""
    print("\n" + "="*60)
    print("TEST 9: Detailed Metrics")
    print("="*60)
    
    account = {"equity": 100000, "cash": 50000}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 148.00,
        "target_level": 155.00,
    }
    config = {"max_risk_pct": 0.01}
    
    result = evaluate(account, signal, config)
    
    print(f"Allowed: {result['allowed']}")
    print(f"Shares: {result['shares']}")
    print(f"Entry Price: {result.get('entry_price')}")
    print(f"Stop Price: {result.get('stop_price')}")
    print(f"Target Price: {result.get('target_price')}")
    print(f"Risk per share: {result.get('risk_per_share')}")
    print(f"Max risk dollars: {result.get('max_risk_dollars')}")
    print(f"Risk dollars: {result.get('risk_dollars')}")
    
    assert result["allowed"] is True, "Should allow trade"
    assert "entry_price" in result, "Should return entry price"
    assert "stop_price" in result, "Should return stop price"
    assert "risk_dollars" in result, "Should return risk dollars"
    print("✓ Test passed")
    return True


def test_zero_equity():
    """Test: Trade rejected with zero equity."""
    print("\n" + "="*60)
    print("TEST 10: Zero Equity")
    print("="*60)
    
    account = {"equity": 0, "cash": 0}
    signal = {
        "action": "BUY",
        "entry_level": 150.00,
        "stop_level": 149.00,
    }
    config = {}
    
    result = evaluate(account, signal, config)
    
    print(f"Equity: $0")
    print(f"Allowed: {result['allowed']}")
    print(f"Reason: {result['reason']}")
    
    assert result["allowed"] is False, "Should reject zero equity"
    assert "equity" in result["reason"].lower(), "Should mention equity"
    print("✓ Test passed")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("RISK MANAGER TEST SUITE")
    print("="*60)
    
    tests = [
        ("No Signal", test_no_signal),
        ("Basic BUY Signal", test_basic_buy_signal),
        ("Max Daily Trades", test_max_daily_trades),
        ("Insufficient Buying Power", test_insufficient_buying_power),
        ("Max Position Size", test_max_position_size),
        ("Max Open Risk", test_max_open_risk),
        ("Invalid Stop Loss", test_invalid_stop_loss),
        ("Missing Prices", test_missing_prices),
        ("Detailed Metrics", test_detailed_metrics),
        ("Zero Equity", test_zero_equity),
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
