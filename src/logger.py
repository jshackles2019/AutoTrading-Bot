"""Logging and journaling for Breakout Trading Bot.

Provides file-based logging and CSV trade journaling for signals, orders, fills, and PnL.
"""

import logging
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class BotLogger:
    """Unified logger for Breakout Trading Bot.
    
    Logs to both text files and structured CSV for trade history.
    """
    
    def __init__(self, log_dir: Optional[str] = None, trades_dir: Optional[str] = None):
        """Initialize logger with file paths.
        
        Args:
            log_dir: Directory for text/JSON logs (defaults to data/logs)
            trades_dir: Directory for CSV trade history (defaults to data/trades)
        """
        if log_dir is None:
            log_dir = str(Path(__file__).resolve().parents[1] / "data" / "logs")
        if trades_dir is None:
            trades_dir = str(Path(__file__).resolve().parents[1] / "data" / "trades")
        
        self.log_dir = Path(log_dir)
        self.trades_dir = Path(trades_dir)
        
        # Create directories if they don't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize logger
        self.logger = logging.getLogger("BreakoutBot")
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler (rotating logs daily)
        log_file = self.log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler (INFO level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # CSV trade logger
        self.trades_csv = self.trades_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.csv"
        self._init_trades_csv()
    
    def _init_trades_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.trades_csv.exists():
            with open(self.trades_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "timestamp",
                    "symbol",
                    "side",
                    "entry_price",
                    "stop_loss",
                    "take_profit",
                    "shares",
                    "order_id",
                    "status",
                    "filled_price",
                    "filled_qty",
                    "exit_price",
                    "pnl",
                    "pnl_pct",
                    "notes",
                ])
                writer.writeheader()
    
    def log_signal(self, symbol: str, signal: Dict[str, Any]):
        """Log a breakout signal.
        
        Args:
            symbol: Stock symbol
            signal: Signal dict with action, entry_level, stop_level, target_level, etc.
        """
        action = signal.get("action", "NONE")
        entry = signal.get("entry_level", "N/A")
        stop = signal.get("stop_level", "N/A")
        target = signal.get("target_level", "N/A")
        volume_check = signal.get("volume_check", False)
        
        msg = f"SIGNAL | {symbol} | Action: {action} | Entry: {entry} | Stop: {stop} | Target: {target} | Volume Check: {volume_check}"
        self.logger.info(msg)
    
    def log_order(self, order: Dict[str, Any]):
        """Log an order submission.
        
        Args:
            order: Order details from alpaca_client.submit_order()
        """
        symbol = order.get("symbol", "N/A")
        side = order.get("side", "N/A")
        qty = order.get("qty", "N/A")
        status = order.get("status", "N/A")
        order_id = order.get("id", "N/A")
        
        msg = f"ORDER | {symbol} {side.upper()} {qty} | Status: {status} | ID: {order_id}"
        self.logger.info(msg)
        
        # Write to trades CSV (initial row)
        self._append_trade_row({
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "order_id": order_id,
            "status": "submitted",
        })
    
    def log_fill(self, symbol: str, order_details: Dict[str, Any]):
        """Log order fill.
        
        Args:
            symbol: Stock symbol
            order_details: Order details including filled_qty, filled_avg_price, etc.
        """
        filled_qty = order_details.get("filled_qty", 0)
        filled_price = order_details.get("filled_avg_price", "N/A")
        order_id = order_details.get("id", "N/A")
        
        msg = f"FILL | {symbol} | {filled_qty} @ {filled_price} | ID: {order_id}"
        self.logger.info(msg)
        
        # Update trades CSV
        self._update_trade_row(order_id, {
            "filled_qty": filled_qty,
            "filled_price": filled_price,
            "status": "filled",
        })
    
    def log_trade_entry(self, symbol: str, entry_price: float, stop_loss: float,
                       take_profit: float, shares: int, order_id: str):
        """Log a completed trade entry.
        
        Args:
            symbol: Stock symbol
            entry_price: Entry price
            stop_loss: Stop loss level
            take_profit: Take profit level
            shares: Number of shares
            order_id: Order ID
        """
        msg = f"ENTRY | {symbol} | Price: {entry_price} | Shares: {shares} | Stop: {stop_loss} | Target: {take_profit}"
        self.logger.info(msg)
        
        self._append_trade_row({
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "shares": shares,
            "order_id": order_id,
            "status": "active",
        })
    
    def log_exit(self, symbol: str, exit_price: float, pnl: float, pnl_pct: float,
                order_id: Optional[str] = None, reason: str = "manual"):
        """Log a trade exit / close.
        
        Args:
            symbol: Stock symbol
            exit_price: Exit price
            pnl: Profit/loss in dollars
            pnl_pct: Profit/loss percentage
            order_id: Associated order ID (optional)
            reason: Reason for exit (stop_loss, take_profit, manual, timeout, etc.)
        """
        pnl_fmt = f"{pnl:+.2f}"
        pnl_pct_fmt = f"{pnl_pct:+.2f}%"
        msg = f"EXIT | {symbol} | Price: {exit_price} | P&L: {pnl_fmt} ({pnl_pct_fmt}) | Reason: {reason}"
        self.logger.info(msg)
        
        self._update_trade_row(order_id or symbol, {
            "exit_price": exit_price,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "status": f"closed_{reason}",
        })
    
    def log_skip(self, symbol: str, reason: str):
        """Log a skipped trade signal.
        
        Args:
            symbol: Stock symbol
            reason: Why the trade was skipped
        """
        msg = f"SKIP | {symbol} | Reason: {reason}"
        self.logger.debug(msg)
    
    def log_no_signal(self, symbol: str):
        """Log when no signal is generated.
        
        Args:
            symbol: Stock symbol
        """
        msg = f"NO_SIGNAL | {symbol}"
        self.logger.debug(msg)
    
    def log_error(self, message: str, exc_info: Optional[Exception] = None):
        """Log an error.
        
        Args:
            message: Error message
            exc_info: Optional exception object for traceback
        """
        if exc_info:
            self.logger.exception(message)
        else:
            self.logger.error(message)
    
    def log_positions(self, positions: List[Dict[str, Any]]):
        """Log current open positions.
        
        Args:
            positions: List of positions from alpaca_client.get_open_positions()
        """
        if not positions:
            self.logger.info("POSITIONS | No open positions")
            return
        
        self.logger.info(f"POSITIONS | {len(positions)} position(s):")
        for pos in positions:
            symbol = pos.get("symbol", "N/A")
            qty = pos.get("qty", 0)
            entry = pos.get("entry_price", "N/A")
            current = pos.get("current_price", "N/A")
            pl = pos.get("unrealized_pl", 0)
            pl_pct = pos.get("unrealized_plpc", 0)
            msg = f"  {symbol}: {qty} @ {entry} (current: {current}) | P&L: {pl:+.2f} ({pl_pct:+.2f}%)"
            self.logger.info(msg)
    
    def log_summary(self, start_time: datetime, end_time: datetime, 
                   trades_closed: int, total_pnl: float, win_rate: float):
        """Log a session summary.
        
        Args:
            start_time: Session start time
            end_time: Session end time
            trades_closed: Number of completed trades
            total_pnl: Total P&L
            win_rate: Win rate percentage
        """
        duration = end_time - start_time
        msg = f"SUMMARY | Duration: {duration} | Trades: {trades_closed} | P&L: {total_pnl:+.2f} | Win Rate: {win_rate:.1f}%"
        self.logger.info(msg)
    
    def _append_trade_row(self, row: Dict[str, Any]):
        """Append a row to the trades CSV."""
        try:
            with open(self.trades_csv, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "timestamp", "symbol", "side", "entry_price", "stop_loss",
                    "take_profit", "shares", "order_id", "status", "filled_price",
                    "filled_qty", "exit_price", "pnl", "pnl_pct", "notes",
                ])
                writer.writerow(row)
        except Exception as e:
            self.logger.error(f"Failed to write trade row: {e}")
    
    def _update_trade_row(self, order_id: str, updates: Dict[str, Any]):
        """Update an existing trade row (simple implementation).
        
        Note: This is a simplified update. For production, consider SQLite.
        """
        try:
            rows = []
            with open(self.trades_csv, "r", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            
            # Find and update row
            for row in rows:
                if row.get("order_id") == order_id or row.get("symbol") == order_id:
                    row.update(updates)
                    break
            
            # Write back
            with open(self.trades_csv, "w", newline="") as f:
                fieldnames = [
                    "timestamp", "symbol", "side", "entry_price", "stop_loss",
                    "take_profit", "shares", "order_id", "status", "filled_price",
                    "filled_qty", "exit_price", "pnl", "pnl_pct", "notes",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except Exception as e:
            self.logger.error(f"Failed to update trade row: {e}")


# Global logger instance
_logger_instance = None


def get_logger(log_dir: Optional[str] = None, trades_dir: Optional[str] = None) -> BotLogger:
    """Get or create the global logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = BotLogger(log_dir, trades_dir)
    return _logger_instance
