#!/usr/bin/env python3
"""Main entry point for Breakout Trading Bot.

Implements the core trading loop that monitors symbols, generates signals,
manages risk, and executes trades during market hours.
"""

import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from src import alpaca_client, utils
    from src.strategy_breakout import evaluate as evaluate_strategy
    from src.risk_manager import evaluate as evaluate_risk
    from src.executor import submit_order, close_position
    from src.logger import get_logger
except ImportError:
    import alpaca_client
    import utils
    from strategy_breakout import evaluate as evaluate_strategy
    from risk_manager import evaluate as evaluate_risk
    from executor import submit_order, close_position
    from logger import get_logger


class TradingSession:
    """Manages a single trading session."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize trading session.
        
        Args:
            config: Configuration dictionary from settings.yaml
        """
        self.config = config
        self.logger = get_logger()
        
        # Trading state
        self.trades_today = 0
        self.open_risk_dollars = 0.0
        self.active_trades = {}  # symbol -> trade details
        self.session_start = datetime.now()
        self.session_pnl = 0.0
        self.trades_closed = 0
        self.wins = 0
    
    def run(self):
        """Run the main trading loop."""
        self.logger.logger.info("="*60)
        self.logger.logger.info("TRADING SESSION STARTED")
        self.logger.logger.info("="*60)
        
        try:
            # Get account info
            account = alpaca_client.get_account()
            self.logger.logger.info(f"Account equity: ${account['equity']:,.2f}")
            self.logger.logger.info(f"Buying power: ${account['buying_power']:,.2f}")
            
            # Main loop
            loop_count = 0
            loop_interval = self.config.get("loop_interval_seconds", 60)
            
            while utils.is_market_open():
                loop_count += 1
                self.logger.logger.debug(f"\n--- Loop {loop_count} ---")
                
                try:
                    self._loop_iteration(account)
                except Exception as e:
                    self.logger.log_error(f"Error in loop iteration: {e}", exc_info=e)
                
                # Check remaining market time
                remaining = utils.market_hours_remaining()
                if remaining.total_seconds() < loop_interval:
                    self.logger.logger.info(f"Market closing soon ({remaining}). Skipping sleep.")
                    break
                
                # Sleep before next iteration
                self.logger.logger.debug(f"Sleeping for {loop_interval}s...")
                time.sleep(loop_interval)
        
        except KeyboardInterrupt:
            self.logger.logger.info("Trading interrupted by user")
        except Exception as e:
            self.logger.log_error(f"Fatal error in trading loop: {e}", exc_info=e)
        finally:
            self._close_session()
    
    def _loop_iteration(self, account: Dict[str, Any]):
        """Execute one iteration of the trading loop.
        
        Args:
            account: Current account information
        """
        symbols = self.config.get("symbols", [])
        timeframe = self.config.get("timeframe", "5Min")
        lookback = self.config.get("lookback", 50)
        
        # Check active positions for exits
        self._check_exits(account)
        
        # Scan for new signals
        for symbol in symbols:
            try:
                self._evaluate_symbol(symbol, timeframe, lookback, account)
            except Exception as e:
                self.logger.log_error(f"Error evaluating {symbol}: {e}", exc_info=e)
    
    def _evaluate_symbol(self, symbol: str, timeframe: str, lookback: int,
                        account: Dict[str, Any]):
        """Evaluate a single symbol for breakout signals.
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe (e.g., '5Min')
            lookback: Number of bars to retrieve
            account: Current account information
        """
        # Fetch bars
        bars = alpaca_client.get_bars(symbol, timeframe, lookback)
        if not bars:
            self.logger.logger.warning(f"No bars for {symbol}")
            return
        
        # Evaluate strategy
        signal = evaluate_strategy(bars, symbol)
        self.logger.log_signal(symbol, signal)
        
        if signal["action"] != "BUY":
            self.logger.log_no_signal(symbol)
            return
        
        # Evaluate risk
        risk_config = self.config.get("risk", {})
        risk_config["current_trades_today"] = self.trades_today
        risk_config["current_open_risk"] = self.open_risk_dollars
        
        risk_decision = evaluate_risk(account, signal, risk_config)
        
        if not risk_decision.get("allowed"):
            reason = risk_decision.get("reason", "Unknown reason")
            self.logger.log_skip(symbol, reason)
            return
        
        # Execute trade
        self._execute_buy(symbol, signal, risk_decision)
    
    def _execute_buy(self, symbol: str, signal: Dict[str, Any],
                    risk_decision: Dict[str, Any]):
        """Execute a buy order.
        
        Args:
            symbol: Stock symbol
            signal: Strategy signal
            risk_decision: Risk manager decision
        """
        shares = risk_decision.get("shares")
        entry_price = signal.get("entry_level")
        stop_loss = signal.get("stop_level")
        target = signal.get("target_level")
        
        # Build order
        order_params = {
            "symbol": symbol,
            "qty": shares,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "stop_loss": stop_loss,
            "take_profit": target,
        }
        
        try:
            # Submit order
            order = submit_order(order_params, logger=self.logger)
            order_id = order.get("id")
            
            # Track trade
            risk_dollars = risk_decision.get("risk_dollars", 0)
            self.active_trades[symbol] = {
                "order_id": order_id,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target": target,
                "shares": shares,
                "entry_time": datetime.now(),
                "risk_dollars": risk_dollars,
            }
            
            self.trades_today += 1
            self.open_risk_dollars += risk_dollars
            
            self.logger.log_trade_entry(symbol, entry_price, stop_loss, target,
                                       shares, order_id)
            
            self.logger.logger.info(f"Trades today: {self.trades_today} | "
                                   f"Open risk: ${self.open_risk_dollars:,.2f}")
        
        except Exception as e:
            self.logger.log_error(f"Failed to execute buy for {symbol}: {e}", exc_info=e)
    
    def _check_exits(self, account: Dict[str, Any]):
        """Check active positions for exit conditions.
        
        Args:
            account: Current account information
        """
        positions = alpaca_client.get_open_positions()
        position_map = {p["symbol"]: p for p in positions}
        
        # Check each active trade
        symbols_to_remove = []
        for symbol, trade in self.active_trades.items():
            if symbol not in position_map:
                # Position was closed externally
                self.logger.logger.info(f"{symbol} position closed externally")
                symbols_to_remove.append(symbol)
                continue
            
            position = position_map[symbol]
            current_price = position["current_price"]
            entry_price = trade["entry_price"]
            stop_loss = trade["stop_loss"]
            target = trade["target"]
            
            # Check stop loss
            if current_price <= stop_loss:
                self._close_trade(symbol, current_price, "stop_loss")
                symbols_to_remove.append(symbol)
                continue
            
            # Check target
            if current_price >= target:
                self._close_trade(symbol, current_price, "take_profit")
                symbols_to_remove.append(symbol)
                continue
            
            # Check timeout (e.g., hold for max 1 hour per trade)
            max_hold_minutes = self.config.get("max_hold_minutes", 60)
            hold_duration = datetime.now() - trade["entry_time"]
            if hold_duration.total_seconds() > max_hold_minutes * 60:
                self.logger.logger.info(f"{symbol} timeout - held for {max_hold_minutes}m")
                self._close_trade(symbol, current_price, "timeout")
                symbols_to_remove.append(symbol)
        
        # Remove closed trades from tracking
        for symbol in symbols_to_remove:
            trade = self.active_trades.pop(symbol)
            self.open_risk_dollars -= trade.get("risk_dollars", 0)
    
    def _close_trade(self, symbol: str, exit_price: float, reason: str):
        """Close a trade.
        
        Args:
            symbol: Stock symbol
            exit_price: Price at exit
            reason: Reason for exit (stop_loss, take_profit, timeout, etc.)
        """
        if symbol not in self.active_trades:
            return
        
        trade = self.active_trades[symbol]
        entry_price = trade["entry_price"]
        shares = trade["shares"]
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        
        try:
            # Close position
            close_position(symbol, qty=shares, logger=self.logger)
            
            # Log exit
            self.logger.log_exit(symbol, exit_price, pnl, pnl_pct,
                               order_id=trade["order_id"], reason=reason)
            
            # Update session stats
            self.session_pnl += pnl
            self.trades_closed += 1
            if pnl > 0:
                self.wins += 1
            
            self.logger.logger.info(f"Trade closed: {symbol} | "
                                   f"P&L: {pnl:+.2f} ({pnl_pct:+.2f}%) | "
                                   f"Session P&L: {self.session_pnl:+.2f}")
        
        except Exception as e:
            self.logger.log_error(f"Failed to close {symbol}: {e}", exc_info=e)
    
    def _close_session(self):
        """Close the trading session and log summary."""
        self.logger.logger.info("="*60)
        self.logger.logger.info("CLOSING TRADING SESSION")
        self.logger.logger.info("="*60)
        
        # Log summary
        session_end = datetime.now()
        duration = session_end - self.session_start
        win_rate = (self.wins / self.trades_closed * 100) if self.trades_closed > 0 else 0
        
        self.logger.log_summary(self.session_start, session_end, self.trades_closed,
                               self.session_pnl, win_rate)
        
        # Log final positions
        try:
            positions = alpaca_client.get_open_positions()
            self.logger.log_positions(positions)
        except Exception as e:
            self.logger.log_error(f"Failed to fetch final positions: {e}")
        
        self.logger.logger.info("="*60)
        self.logger.logger.info("SESSION ENDED")
        self.logger.logger.info("="*60)


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("BREAKOUT TRADING BOT")
    print("="*60)
    
    try:
        # Load configuration
        print("Loading configuration...")
        config = utils.load_config()
        print(f"✓ Config loaded")
        print(f"  Symbols: {config.get('symbols')}")
        print(f"  Timeframe: {config.get('timeframe')}")
        print(f"  Max trades/day: {config.get('risk', {}).get('max_trades_per_day')}")
        
        # Check if market is open
        print(f"\nChecking market status...")
        now = utils.now_market()
        print(f"  Current time: {now}")
        print(f"  Market open: {utils.is_market_open()}")
        
        if not utils.is_market_open():
            next_open = utils.next_market_open()
            print(f"\n✗ Market is closed. Next open: {next_open}")
            return 1
        
        # Start trading session
        print(f"\n✓ Market is open. Starting trading session...")
        session = TradingSession(config)
        session.run()
        
        return 0
    
    except FileNotFoundError as e:
        print(f"✗ Configuration error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
