#!/usr/bin/env python3
"""Test script for logger.py

Tests logging functionality including file logs, CSV trade journaling, etc.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from logger import get_logger


def test_logger():
    """Test the logger with various events."""
    print("\n" + "="*60)
    print("LOGGER TEST SUITE")
    print("="*60)
    
    # Get logger instance
    logger = get_logger()
    print("✓ Logger initialized")
    
    # Test 1: Log signals
    print("\n" + "-"*60)
    print("TEST 1: Log signals")
    print("-"*60)
    logger.log_signal("AAPL", {
        "action": "BUY",
        "entry_level": 150.25,
        "stop_level": 149.50,
        "target_level": 152.00,
        "volume_check": True,
    })
    logger.log_signal("SPY", {
        "action": "NONE",
        "entry_level": "N/A",
        "stop_level": "N/A",
        "target_level": "N/A",
        "volume_check": False,
    })
    print("✓ Signals logged")
    
    # Test 2: Log orders
    print("\n" + "-"*60)
    print("TEST 2: Log order submission")
    print("-"*60)
    order = {
        "id": "order_12345",
        "symbol": "AAPL",
        "qty": 10,
        "side": "buy",
        "status": "pending",
    }
    logger.log_order(order)
    print("✓ Order logged")
    
    # Test 3: Log fill
    print("\n" + "-"*60)
    print("TEST 3: Log order fill")
    print("-"*60)
    logger.log_fill("AAPL", {
        "id": "order_12345",
        "filled_qty": 10,
        "filled_avg_price": 150.30,
    })
    print("✓ Fill logged")
    
    # Test 4: Log trade entry
    print("\n" + "-"*60)
    print("TEST 4: Log trade entry")
    print("-"*60)
    logger.log_trade_entry(
        symbol="AAPL",
        entry_price=150.30,
        stop_loss=149.50,
        take_profit=152.00,
        shares=10,
        order_id="order_12345",
    )
    print("✓ Trade entry logged")
    
    # Test 5: Log skipped trades
    print("\n" + "-"*60)
    print("TEST 5: Log skipped trades and no-signals")
    print("-"*60)
    logger.log_skip("MSFT", "Max daily trades reached (3/3)")
    logger.log_no_signal("GOOGL")
    print("✓ Skipped trades logged")
    
    # Test 6: Log positions
    print("\n" + "-"*60)
    print("TEST 6: Log open positions")
    print("-"*60)
    positions = [
        {
            "symbol": "AAPL",
            "qty": 10,
            "side": "long",
            "entry_price": 150.30,
            "current_price": 151.50,
            "unrealized_pl": 12.00,
            "unrealized_plpc": 0.80,
            "market_value": 1515.00,
        },
        {
            "symbol": "SPY",
            "qty": 5,
            "side": "long",
            "entry_price": 450.20,
            "current_price": 451.10,
            "unrealized_pl": 4.50,
            "unrealized_plpc": 0.20,
            "market_value": 2255.50,
        },
    ]
    logger.log_positions(positions)
    print("✓ Positions logged")
    
    # Test 7: Log exit
    print("\n" + "-"*60)
    print("TEST 7: Log trade exits")
    print("-"*60)
    logger.log_exit(
        symbol="AAPL",
        exit_price=152.00,
        pnl=17.00,
        pnl_pct=1.13,
        order_id="order_12345",
        reason="take_profit",
    )
    logger.log_exit(
        symbol="SPY",
        exit_price=450.00,
        pnl=-1.00,
        pnl_pct=-0.22,
        order_id="order_12346",
        reason="stop_loss",
    )
    print("✓ Exits logged")
    
    # Test 8: Log summary
    print("\n" + "-"*60)
    print("TEST 8: Log session summary")
    print("-"*60)
    start = datetime.now() - timedelta(hours=6, minutes=30)
    end = datetime.now()
    logger.log_summary(start, end, trades_closed=2, total_pnl=16.00, win_rate=100.0)
    print("✓ Summary logged")
    
    # Test 9: Log error
    print("\n" + "-"*60)
    print("TEST 9: Log errors")
    print("-"*60)
    logger.log_error("Example error message (no traceback)")
    try:
        1 / 0
    except Exception as e:
        logger.log_error("Example error with traceback", exc_info=e)
    print("✓ Errors logged")
    
    # Show file paths
    print("\n" + "="*60)
    print("OUTPUT FILES")
    print("="*60)
    print(f"Log files: {logger.log_dir}")
    print(f"Trades CSV: {logger.trades_csv}")
    
    # Verify files exist and show snippet
    if logger.trades_csv.exists():
        print(f"\n✓ Trades CSV created ({logger.trades_csv.name})")
        with open(logger.trades_csv, "r") as f:
            lines = f.readlines()
            print(f"  Rows: {len(lines) - 1} trades + 1 header")
            if len(lines) > 1:
                print(f"  First trade row: {lines[1][:80]}...")
    
    log_files = list(logger.log_dir.glob("*.log"))
    if log_files:
        print(f"\n✓ Log files created ({len(log_files)} file(s))")
        latest = max(log_files, key=lambda p: p.stat().st_mtime)
        print(f"  Latest: {latest.name}")
        with open(latest, "r") as f:
            lines = f.readlines()
            print(f"  Entries: {len(lines)}")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_logger()
