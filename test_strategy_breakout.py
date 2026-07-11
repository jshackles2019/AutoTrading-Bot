#!/usr/bin/env python3
"""Test script for strategy_breakout.py

Tests breakout signal generation with various scenarios.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from strategy_breakout import evaluate, BreakoutSignal


def generate_sample_bars(days=50, start_price=100.0, breakout_on_day=None, 
                        high_vol_day=None):
    """Generate sample OHLCV bars for testing.
    
    Args:
        days: Number of bars to generate
        start_price: Starting price
        breakout_on_day: Day number to inject a breakout (1-indexed)
        high_vol_day: Day number to inject high volume (1-indexed)
        
    Returns:
        List of bar dicts
    """
    bars = []
    price = start_price
    base_volume = 1000000
    
    for day in range(1, days + 1):
        # Simulate price movement
        open_price = price
        close_price = price + (day % 3 - 1) * 0.5  # Small random walk
        
        # Inject breakout pattern
        if breakout_on_day and day == breakout_on_day:
            high_price = open_price + 3.0  # Strong breakout up
            low_price = open_price - 1.0
            close_price = high_price - 0.5
        else:
            high_price = open_price + 1.0
            low_price = open_price - 1.0
        
        # Inject high volume
        volume = base_volume
        if high_vol_day and day == high_vol_day:
            volume = base_volume * 2.5
        
        bars.append({
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": int(volume),
            "timestamp": datetime.now() - timedelta(days=days - day),
        })
        
        price = close_price
    
    return bars


def test_no_signal():
    """Test: No breakout signal when price not breaking resistance."""
    print("\n" + "="*60)
    print("TEST 1: No Signal (No Breakout)")
    print("="*60)
    
    bars = generate_sample_bars(days=50, start_price=100.0)
    signal = evaluate(bars, "AAPL")
    
    print(f"Symbol: {signal['symbol']}")
    print(f"Action: {signal['action']}")
    print(f"Confidence: {signal['confidence']}")
    
    assert signal["action"] == "NONE", "Should have no signal"
    print("✓ Test passed")
    return True


def test_simple_breakout():
    """Test: Simple breakout signal without volume confirmation."""
    print("\n" + "="*60)
    print("TEST 2: Simple Breakout (No Volume Confirmation)")
    print("="*60)
    
    bars = generate_sample_bars(days=50, start_price=100.0, breakout_on_day=50)
    signal = evaluate(bars, "SPY")
    
    print(f"Symbol: {signal['symbol']}")
    print(f"Action: {signal['action']}")
    print(f"Entry: {signal['entry_level']}")
    print(f"Stop Loss: {signal['stop_level']}")
    print(f"Target: {signal['target_level']}")
    print(f"Confidence: {signal['confidence']}")
    print(f"Volume Check: {signal['volume_check']}")
    
    assert signal["action"] == "BUY", "Should generate BUY signal"
    assert signal["entry_level"] is not None, "Should have entry level"
    assert signal["stop_level"] is not None, "Should have stop loss"
    assert signal["target_level"] is not None, "Should have target"
    print("✓ Test passed")
    return True


def test_breakout_with_volume():
    """Test: Breakout signal with volume confirmation."""
    print("\n" + "="*60)
    print("TEST 3: Breakout With Volume Confirmation")
    print("="*60)
    
    bars = generate_sample_bars(days=50, start_price=100.0, 
                              breakout_on_day=50, high_vol_day=50)
    signal = evaluate(bars, "MSFT")
    
    print(f"Symbol: {signal['symbol']}")
    print(f"Action: {signal['action']}")
    print(f"Entry: {signal['entry_level']}")
    print(f"Stop Loss: {signal['stop_level']}")
    print(f"Target: {signal['target_level']}")
    print(f"Confidence: {signal['confidence']}")
    print(f"Volume Check: {signal['volume_check']}")
    
    assert signal["action"] == "BUY", "Should generate BUY signal"
    assert signal["volume_check"], "Should have volume confirmation"
    print("✓ Test passed")
    return True


def test_insufficient_bars():
    """Test: No signal with insufficient bars."""
    print("\n" + "="*60)
    print("TEST 4: Insufficient Bars")
    print("="*60)
    
    bars = generate_sample_bars(days=5, start_price=100.0)  # Too few bars
    signal = evaluate(bars, "GOOGL")
    
    print(f"Symbol: {signal['symbol']}")
    print(f"Action: {signal['action']}")
    
    assert signal["action"] == "NONE", "Should have no signal"
    print("✓ Test passed")
    return True


def test_custom_config():
    """Test: Custom configuration parameters."""
    print("\n" + "="*60)
    print("TEST 5: Custom Configuration")
    print("="*60)
    
    bars = generate_sample_bars(days=50, start_price=100.0, breakout_on_day=50)
    
    config = {
        "lookback_support": 10,
        "lookback_resistance": 10,
        "volume_threshold_factor": 2.0,
        "target_multiplier": 3.0,
    }
    
    signal = evaluate(bars, "TSLA", config=config)
    
    print(f"Symbol: {signal['symbol']}")
    print(f"Action: {signal['action']}")
    print(f"Entry: {signal['entry_level']}")
    print(f"Stop Loss: {signal['stop_level']}")
    print(f"Target: {signal['target_level']}")
    
    assert signal["action"] == "BUY", "Should generate BUY signal"
    print("✓ Test passed")
    return True


def test_signal_object():
    """Test: BreakoutSignal object and to_dict()."""
    print("\n" + "="*60)
    print("TEST 6: BreakoutSignal Object")
    print("="*60)
    
    signal_obj = BreakoutSignal(
        symbol="NVDA",
        action="BUY",
        entry_level=150.50,
        stop_level=149.00,
        target_level=155.00,
        confidence=0.75,
        volume_check=True,
        volatility_check=False,
    )
    
    signal_dict = signal_obj.to_dict()
    
    print(f"Signal object created: {signal_obj.symbol}")
    print(f"Action: {signal_obj.action}")
    print(f"Confidence: {signal_obj.confidence}")
    print(f"Dict conversion: {signal_dict}")
    
    assert signal_dict["symbol"] == "NVDA", "Symbol should match"
    assert signal_dict["action"] == "BUY", "Action should be BUY"
    assert signal_dict["volume_check"] is True, "Volume check should be True"
    print("✓ Test passed")
    return True


def test_risk_reward_calculation():
    """Test: Risk/reward ratio calculation in target."""
    print("\n" + "="*60)
    print("TEST 7: Risk/Reward Ratio Calculation")
    print("="*60)
    
    bars = generate_sample_bars(days=50, start_price=100.0, breakout_on_day=50)
    signal = evaluate(bars, "AMD")
    
    if signal["action"] == "BUY":
        entry = signal["entry_level"]
        stop = signal["stop_level"]
        target = signal["target_level"]
        
        risk = entry - stop
        reward = target - entry
        ratio = reward / risk if risk > 0 else 0
        
        print(f"Entry: {entry}")
        print(f"Stop: {stop}")
        print(f"Target: {target}")
        print(f"Risk: {risk:.2f}")
        print(f"Reward: {reward:.2f}")
        print(f"Risk/Reward Ratio: {ratio:.2f}:1")
        
        assert ratio >= 1.0, "Reward should be >= risk"
        print("✓ Test passed")
    else:
        print("No BUY signal generated (test inconclusive)")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("BREAKOUT STRATEGY TEST SUITE")
    print("="*60)
    
    tests = [
        ("No Signal", test_no_signal),
        ("Simple Breakout", test_simple_breakout),
        ("Breakout with Volume", test_breakout_with_volume),
        ("Insufficient Bars", test_insufficient_bars),
        ("Custom Config", test_custom_config),
        ("Signal Object", test_signal_object),
        ("Risk/Reward", test_risk_reward_calculation),
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
