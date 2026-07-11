#!/usr/bin/env python3
"""Test script for executor.py

Tests order building, submission, and position closing logic.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from executor import build_order_payload, submit_order, close_position


def test_build_market_order():
    """Test: Build a market order payload."""
    print("\n" + "="*60)
    print("TEST 1: Build Market Order")
    print("="*60)
    
    payload = build_order_payload(
        symbol="AAPL",
        qty=10,
        side="buy",
        order_type="market",
    )
    
    print(f"Payload: {payload}")
    
    assert payload["symbol"] == "AAPL", "Symbol should match"
    assert payload["qty"] == 10, "Quantity should be 10"
    assert payload["side"] == "buy", "Side should be buy"
    assert payload["type"] == "market", "Type should be market"
    print("✓ Test passed")
    return True


def test_build_limit_order():
    """Test: Build a limit order payload."""
    print("\n" + "="*60)
    print("TEST 2: Build Limit Order")
    print("="*60)
    
    payload = build_order_payload(
        symbol="SPY",
        qty=5,
        side="sell",
        order_type="limit",
        limit_price=450.50,
    )
    
    print(f"Payload: {payload}")
    
    assert payload["symbol"] == "SPY", "Symbol should match"
    assert payload["qty"] == 5, "Quantity should be 5"
    assert payload["side"] == "sell", "Side should be sell"
    assert payload["type"] == "limit", "Type should be limit"
    assert payload["limit_price"] == 450.50, "Limit price should match"
    print("✓ Test passed")
    return True


def test_build_order_with_bracket():
    """Test: Build order with stop loss and take profit."""
    print("\n" + "="*60)
    print("TEST 3: Build Order With Bracket (Stop/Target)")
    print("="*60)
    
    payload = build_order_payload(
        symbol="MSFT",
        qty=20,
        side="buy",
        order_type="market",
        stop_loss=300.00,
        take_profit=310.00,
    )
    
    print(f"Payload: {payload}")
    
    assert payload["stop_loss"] == 300.00, "Stop loss should match"
    assert payload["take_profit"] == 310.00, "Take profit should match"
    print("✓ Test passed")
    return True


def test_invalid_side():
    """Test: Invalid side raises error."""
    print("\n" + "="*60)
    print("TEST 4: Invalid Side")
    print("="*60)
    
    try:
        payload = build_order_payload(
            symbol="AAPL",
            qty=10,
            side="invalid",
        )
        print("✗ Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised error: {e}")
        return True


def test_invalid_order_type():
    """Test: Invalid order type raises error."""
    print("\n" + "="*60)
    print("TEST 5: Invalid Order Type")
    print("="*60)
    
    try:
        payload = build_order_payload(
            symbol="AAPL",
            qty=10,
            order_type="invalid",
        )
        print("✗ Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised error: {e}")
        return True


def test_limit_order_missing_price():
    """Test: Limit order without limit_price raises error."""
    print("\n" + "="*60)
    print("TEST 6: Limit Order Missing Price")
    print("="*60)
    
    try:
        payload = build_order_payload(
            symbol="AAPL",
            qty=10,
            order_type="limit",
            # Missing limit_price
        )
        print("✗ Should have raised ValueError")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised error: {e}")
        return True


def test_submit_order_with_mock_client():
    """Test: Submit order with mocked client."""
    print("\n" + "="*60)
    print("TEST 7: Submit Order With Mock Client")
    print("="*60)
    
    mock_client = Mock()
    mock_client.submit_order.return_value = {
        "id": "order_123",
        "symbol": "AAPL",
        "qty": 10,
        "status": "pending",
    }
    
    mock_logger = Mock()
    
    order_params = {
        "symbol": "AAPL",
        "qty": 10,
        "side": "buy",
        "type": "market",
    }
    
    result = submit_order(order_params, client=mock_client, logger=mock_logger)
    
    print(f"Order result: {result}")
    print(f"Client.submit_order called: {mock_client.submit_order.called}")
    print(f"Logger.log_order called: {mock_logger.log_order.called}")
    
    assert result["id"] == "order_123", "Order ID should match"
    assert mock_client.submit_order.called, "Client should be called"
    assert mock_logger.log_order.called, "Logger should be called"
    print("✓ Test passed")
    return True


def test_submit_bracket_order_with_fallback():
    """Test: Bracket order with fallback to normal order."""
    print("\n" + "="*60)
    print("TEST 8: Bracket Order With Fallback")
    print("="*60)
    
    mock_client = Mock()
    mock_client.submit_bracket_order.side_effect = Exception("Bracket not supported")
    mock_client.submit_order.return_value = {
        "id": "order_456",
        "symbol": "SPY",
        "qty": 5,
        "status": "pending",
    }
    
    mock_logger = Mock()
    
    order_params = {
        "symbol": "SPY",
        "qty": 5,
        "side": "buy",
        "type": "market",
        "stop_loss": 450.00,
        "take_profit": 455.00,
    }
    
    result = submit_order(order_params, client=mock_client, logger=mock_logger, use_bracket=True)
    
    print(f"Order result: {result}")
    print(f"Bracket order attempted: {mock_client.submit_bracket_order.called}")
    print(f"Fallback to regular order: {mock_client.submit_order.called}")
    
    assert result["id"] == "order_456", "Should fall back to normal order"
    assert mock_client.submit_bracket_order.called, "Should attempt bracket"
    assert mock_client.submit_order.called, "Should fall back to normal"
    print("✓ Test passed")
    return True


def test_close_position_with_mock():
    """Test: Close position with mocked client."""
    print("\n" + "="*60)
    print("TEST 9: Close Position With Mock Client")
    print("="*60)
    
    mock_client = Mock()
    mock_client.close_position.return_value = {
        "id": "order_789",
        "symbol": "AAPL",
        "qty": 10,
        "side": "sell",
        "status": "filled",
    }
    
    mock_logger = Mock()
    
    result = close_position("AAPL", qty=10, client=mock_client, logger=mock_logger)
    
    print(f"Close result: {result}")
    print(f"Client.close_position called: {mock_client.close_position.called}")
    print(f"Logger.log_order called: {mock_logger.log_order.called}")
    
    assert result["symbol"] == "AAPL", "Symbol should match"
    assert result["side"] == "sell", "Should be sell order"
    assert mock_client.close_position.called, "Client should be called"
    print("✓ Test passed")
    return True


def test_close_position_fallback():
    """Test: Close position fallback when close_position not supported."""
    print("\n" + "="*60)
    print("TEST 10: Close Position Fallback")
    print("="*60)
    
    mock_client = Mock(spec=["submit_order"])  # Only has submit_order
    mock_client.submit_order.return_value = {
        "id": "order_999",
        "symbol": "SPY",
        "qty": 5,
        "side": "sell",
        "status": "pending",
    }
    
    mock_logger = Mock()
    
    result = close_position("SPY", qty=5, client=mock_client, logger=mock_logger)
    
    print(f"Close result: {result}")
    print(f"Client.submit_order called (fallback): {mock_client.submit_order.called}")
    
    assert result["side"] == "sell", "Should be sell order"
    assert mock_client.submit_order.called, "Should fall back to submit_order"
    print("✓ Test passed")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("EXECUTOR TEST SUITE")
    print("="*60)
    
    tests = [
        ("Build Market Order", test_build_market_order),
        ("Build Limit Order", test_build_limit_order),
        ("Build Order With Bracket", test_build_order_with_bracket),
        ("Invalid Side", test_invalid_side),
        ("Invalid Order Type", test_invalid_order_type),
        ("Limit Order Missing Price", test_limit_order_missing_price),
        ("Submit Order With Mock", test_submit_order_with_mock_client),
        ("Bracket Order With Fallback", test_submit_bracket_order_with_fallback),
        ("Close Position With Mock", test_close_position_with_mock),
        ("Close Position Fallback", test_close_position_fallback),
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
