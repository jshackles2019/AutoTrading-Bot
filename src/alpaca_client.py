"""Alpaca client wrapper for Breakout Trading Bot.

Provides high-level functions to interact with Alpaca's trading API using alpaca-py.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import os

try:
    from dotenv import load_dotenv
except Exception:
    # Allow the module to be imported even if python-dotenv isn't installed
    def load_dotenv():
        return
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.enums import Adjustment

load_dotenv()

# Load credentials from .env
ALPACA_KEY = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True").lower() == "true"

if not ALPACA_KEY or not ALPACA_SECRET:
    raise ValueError("ALPACA_KEY_ID and ALPACA_SECRET_KEY must be set in .env")

# Initialize clients
trading_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=ALPACA_PAPER)
data_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)


def get_account() -> Dict[str, Any]:
    """Fetch account information from Alpaca.
    
    Returns:
        Dict with account details including equity, buying_power, cash, etc.
    """
    try:
        account = trading_client.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "multiplier": int(account.multiplier),
            "portfolio_value": float(account.portfolio_value),
            "status": account.status,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to fetch account info: {e}")


def get_bars(symbol: str, timeframe: str, lookback: int = 50) -> List[Dict[str, Any]]:
    """Fetch OHLCV bars for a symbol.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        timeframe: Timeframe string (e.g., '5Min', '1Hour', '1Day')
        lookback: Number of bars to retrieve
        
    Returns:
        List of bars with open, high, low, close, volume, timestamp
    """
    try:
        # Map timeframe string to alpaca-py TimeFrame enum
        timeframe_map = {
            "1Min": "1m",
            "5Min": "5m",
            "15Min": "15m",
            "30Min": "30m",
            "1Hour": "1h",
            "1Day": "1d",
        }
        
        tf = timeframe_map.get(timeframe, timeframe)
        
        # Calculate start time (go back further to account for missing data)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=100)
        
        # Request bars
        request = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=tf,
            start=start_time,
            end=end_time,
            adjustment=Adjustment.RAW,
        )
        
        bars_data = data_client.get_stock_bars(request)
        
        if symbol not in bars_data.data or len(bars_data.data[symbol]) == 0:
            return []
        
        # Extract and sort bars
        bars_list = bars_data.data[symbol]
        bars_list.sort(key=lambda b: b.timestamp)
        
        # Return last 'lookback' bars
        bars = []
        for bar in bars_list[-lookback:]:
            bars.append({
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "timestamp": bar.timestamp,
            })
        
        return bars
    except Exception as e:
        raise RuntimeError(f"Failed to fetch bars for {symbol}: {e}")


def submit_order(order_params: Dict[str, Any]) -> Dict[str, Any]:
    """Submit a market or limit order to Alpaca.
    
    Args:
        order_params: Order details with keys:
            - symbol: Stock symbol
            - qty: Quantity (shares)
            - side: 'buy' or 'sell'
            - type: 'market' or 'limit' (default 'market')
            - limit_price: Required if type='limit'
            - time_in_force: 'day', 'gtc', etc. (default 'day')
            
    Returns:
        Dict with order details (id, symbol, qty, status, etc.)
    """
    try:
        symbol = order_params.get("symbol")
        qty = order_params.get("qty")
        side = order_params.get("side", "buy").lower()
        order_type = order_params.get("type", "market").lower()
        limit_price = order_params.get("limit_price")
        tif = order_params.get("time_in_force", "day").lower()
        
        # Validate inputs
        if not symbol or not qty:
            raise ValueError("symbol and qty are required")
        
        if side not in ["buy", "sell"]:
            raise ValueError("side must be 'buy' or 'sell'")
        
        # Map string to enum
        side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
        tif_enum = TimeInForce.DAY if tif == "day" else TimeInForce.GTC
        
        # Create and submit order
        if order_type == "market":
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=int(qty),
                side=side_enum,
                time_in_force=tif_enum,
            )
        elif order_type == "limit":
            if not limit_price:
                raise ValueError("limit_price required for limit orders")
            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=int(qty),
                side=side_enum,
                limit_price=float(limit_price),
                time_in_force=tif_enum,
            )
        else:
            raise ValueError("type must be 'market' or 'limit'")
        
        order = trading_client.submit_order(order_request)
        
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": int(order.qty),
            "side": order.side.value,
            "status": order.status.value,
            "filled_qty": int(order.filled_qty) if order.filled_qty else 0,
            "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            "created_at": order.created_at,
            "type": order.order_type.value if order.order_type else None,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to submit order: {e}")


def get_open_positions() -> List[Dict[str, Any]]:
    """Fetch all open positions.
    
    Returns:
        List of position dicts with symbol, qty, entry_price, current_price, unrealized_pl, etc.
    """
    try:
        positions = trading_client.get_all_positions()
        
        result = []
        for pos in positions:
            result.append({
                "symbol": pos.symbol,
                "qty": int(pos.qty),
                "side": pos.side.value,
                "entry_price": float(pos.avg_fill_price),
                "current_price": float(pos.current_price),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
                "market_value": float(pos.market_value),
            })
        
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to fetch positions: {e}")


def close_position(symbol: str, qty: Optional[int] = None) -> Dict[str, Any]:
    """Close a position (or reduce it).
    
    Args:
        symbol: Stock symbol to close
        qty: Quantity to close (None = close entire position)
        
    Returns:
        Order details
    """
    try:
        # If qty is None, attempt to use the TradingClient's close_position helper
        if qty is None:
            # Prefer client's close_position if available
            if hasattr(trading_client, "close_position"):
                res = trading_client.close_position(symbol)
                # If the client returned a mapping already, return it
                if isinstance(res, dict):
                    return res
                # Otherwise attempt to normalize the returned object
                try:
                    return {
                        "id": getattr(res, "id", None),
                        "symbol": getattr(res, "symbol", symbol),
                        "qty": int(getattr(res, "qty", 0) or 0),
                        "status": getattr(res, "status", None).value if getattr(res, "status", None) else None,
                        "created_at": getattr(res, "created_at", None),
                    }
                except Exception:
                    return {"symbol": symbol}

            # Fallback: try to discover current position qty and submit a market sell
            try:
                pos = trading_client.get_position(symbol)
                qty_to_close = int(pos.qty)
            except Exception as exc:
                raise RuntimeError(f"Failed to determine position size for {symbol}: {exc}")

            order_params = {
                "symbol": symbol,
                "qty": qty_to_close,
                "side": "sell",
                "type": "market",
                "time_in_force": TimeInForce.DAY,
            }
            return submit_order(order_params)

        # qty provided: submit a market sell for the requested amount
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=int(qty),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )

        order = trading_client.submit_order(order_request)

        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": int(order.qty),
            "status": order.status.value,
            "created_at": order.created_at,
        }
    except Exception as e:
        raise RuntimeError(f"Failed to close position for {symbol}: {e}")
