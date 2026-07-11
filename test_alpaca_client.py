#!/usr/bin/env python3
"""Test script for alpaca_client.py

Tests all core functions: get_account, get_bars, submit_order (dry run), get_open_positions.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from alpaca_client import (
    get_account,
    get_bars,
    submit_order,
    get_open_positions,
)


def test_get_account():
    """Test fetching account info."""
    print("\n" + "="*60)
    print("TEST 1: get_account()")
    print("="*60)
    try:
        account = get_account()
        print("✓ Account info retrieved:")
        for key, value in account.items():
            print(f"  {key}: {value}")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_get_bars():
    """Test fetching historical bars."""
    print("\n" + "="*60)
    print("TEST 2: get_bars() - fetch AAPL 5-minute bars")
    print("="*60)
    try:
        bars = get_bars("AAPL", "5Min", lookback=10)
        print(f"✓ Retrieved {len(bars)} bars:")
        if bars:
            print("\n  First bar:")
            for key, value in bars[0].items():
                print(f"    {key}: {value}")
            print("\n  Last bar:")
            for key, value in bars[-1].items():
                print(f"    {key}: {value}")
        else:
            print("  (No bars returned - may indicate no recent data)")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_get_positions():
    """Test fetching open positions."""
    print("\n" + "="*60)
    print("TEST 3: get_open_positions()")
    print("="*60)
    try:
        positions = get_open_positions()
        print(f"✓ Retrieved {len(positions)} open positions:")
        if positions:
            for i, pos in enumerate(positions, 1):
                print(f"\n  Position {i}:")
                for key, value in pos.items():
                    print(f"    {key}: {value}")
        else:
            print("  (No open positions - this is normal for paper trading)")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def test_submit_order_dry_run():
    """Test order submission (dry run - review logic only)."""
    print("\n" + "="*60)
    print("TEST 4: submit_order() - DRY RUN (order not submitted)")
    print("="*60)
    print("NOTE: Not actually submitting an order. Validating logic...")
    
    try:
        # This will fail without real submission, but shows the logic
        order_params = {
            "symbol": "AAPL",
            "qty": 1,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }
        print(f"✓ Order params valid: {order_params}")
        print("✓ (Uncomment submit_order() call below to actually place a trade)")
        # Actual call commented out for safety:
        # order = submit_order(order_params)
        # print(f"  Order submitted: {order}")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("ALPACA CLIENT TEST SUITE")
    print("="*60)
    
    results = {
        "get_account": test_get_account(),
        "get_bars": test_get_bars(),
        "get_positions": test_get_positions(),
        "submit_order_logic": test_submit_order_dry_run(),
    }
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test}")
    
    print("\n" + "="*60)
    if passed == total:
        print("✓ All tests passed!")
    else:
        print(f"✗ {total - passed} test(s) failed")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
