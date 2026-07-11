"""Utility helpers for Breakout Trading Bot.

Provides configuration loading, time utilities, market hours checking, 
and validation helpers.
"""

import yaml
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import Dict, Any, List, Optional
import pytz


# EST/EDT timezone for US markets
MARKET_TZ = pytz.timezone("America/New_York")
UTC_TZ = pytz.UTC


def get_config_path(config_dir: Optional[str] = None) -> Path:
    """Get the path to settings.yaml configuration file.
    
    Args:
        config_dir: Optional config directory path. Defaults to config/ relative to package root.
        
    Returns:
        Path object pointing to settings.yaml
    """
    if config_dir:
        return Path(config_dir) / "settings.yaml"
    
    # Default: config/settings.yaml relative to src/ parent
    return Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file.
    
    Args:
        config_path: Optional path to settings.yaml. Defaults to config/settings.yaml.
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file not found
        yaml.YAMLError: If config file is invalid YAML
    """
    if not config_path:
        config_path = get_config_path()
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return config or {}
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in {config_path}: {e}")


def now_utc() -> datetime:
    """Get current time in UTC."""
    return datetime.now(UTC_TZ)


def now_market() -> datetime:
    """Get current time in US market timezone (EST/EDT)."""
    return datetime.now(MARKET_TZ)


def now_iso() -> str:
    """Get current UTC time as ISO 8601 string."""
    return now_utc().isoformat()


def is_market_open(check_time: Optional[datetime] = None) -> bool:
    """Check if US stock market is currently open.
    
    Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday (excluding holidays)
    
    Args:
        check_time: Optional datetime to check. Defaults to current time.
        
    Returns:
        True if market is open, False otherwise
    """
    if check_time is None:
        check_time = now_market()
    elif check_time.tzinfo is None:
        # Assume UTC if naive
        check_time = UTC_TZ.localize(check_time).astimezone(MARKET_TZ)
    else:
        # Convert to market timezone
        check_time = check_time.astimezone(MARKET_TZ)
    
    # Market hours: 9:30 AM - 4:00 PM
    market_open_time = time(9, 30, 0)
    market_close_time = time(16, 0, 0)
    
    # Check weekday (0=Monday, 6=Sunday)
    if check_time.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check time within market hours
    current_time = check_time.time()
    return market_open_time <= current_time < market_close_time


def market_hours_remaining(check_time: Optional[datetime] = None) -> timedelta:
    """Calculate time remaining until market close.
    
    Args:
        check_time: Optional datetime to check. Defaults to current time.
        
    Returns:
        Timedelta of remaining time. Returns 0 if market is closed.
    """
    if check_time is None:
        check_time = now_market()
    elif check_time.tzinfo is None:
        check_time = UTC_TZ.localize(check_time).astimezone(MARKET_TZ)
    else:
        check_time = check_time.astimezone(MARKET_TZ)
    
    market_close = check_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if not is_market_open(check_time):
        return timedelta(0)
    
    remaining = market_close - check_time
    return remaining if remaining.total_seconds() > 0 else timedelta(0)


def next_market_open(from_time: Optional[datetime] = None) -> datetime:
    """Calculate the next market open time.
    
    Args:
        from_time: Optional datetime to calculate from. Defaults to current time.
        
    Returns:
        Datetime of next market open (9:30 AM ET)
    """
    if from_time is None:
        from_time = now_market()
    elif from_time.tzinfo is None:
        from_time = UTC_TZ.localize(from_time).astimezone(MARKET_TZ)
    else:
        from_time = from_time.astimezone(MARKET_TZ)
    
    # Set to 9:30 AM on the same day
    next_open = from_time.replace(hour=9, minute=30, second=0, microsecond=0)
    
    # If it's already past 9:30 AM today, go to next day
    if from_time.time() >= time(9, 30, 0):
        next_open += timedelta(days=1)
    
    # Skip weekends
    while next_open.weekday() >= 5:  # 5=Saturday, 6=Sunday
        next_open += timedelta(days=1)
    
    return next_open


def validate_symbol(symbol: str) -> bool:
    """Validate that a symbol is a valid stock symbol format.
    
    Args:
        symbol: Symbol string (e.g., 'AAPL', 'SPY')
        
    Returns:
        True if valid format, False otherwise
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    # Symbol should be 1-5 uppercase letters
    symbol = symbol.strip().upper()
    return 1 <= len(symbol) <= 5 and symbol.isalpha()


def validate_symbols(symbols: List[str]) -> bool:
    """Validate that all symbols are valid.
    
    Args:
        symbols: List of symbol strings
        
    Returns:
        True if all symbols valid, False if any invalid
    """
    if not isinstance(symbols, list) or len(symbols) == 0:
        return False
    
    return all(validate_symbol(s) for s in symbols)


def format_price(price: float, decimals: int = 2) -> str:
    """Format a price as a string with currency symbol.
    
    Args:
        price: Price value
        decimals: Number of decimal places (default 2)
        
    Returns:
        Formatted price string (e.g., "$150.25")
    """
    return f"${price:,.{decimals}f}"


def format_pnl(pnl: float, pnl_pct: float) -> str:
    """Format profit/loss values.
    
    Args:
        pnl: P&L in dollars
        pnl_pct: P&L as percentage
        
    Returns:
        Formatted string (e.g., "+$12.50 (+1.25%)" or "-$5.00 (-0.50%)")
    """
    sign = "+" if pnl >= 0 else ""
    return f"{sign}${pnl:,.2f} ({sign}{pnl_pct:+.2f}%)"


def format_shares(qty: int) -> str:
    """Format share quantity with commas.
    
    Args:
        qty: Number of shares
        
    Returns:
        Formatted string (e.g., "1,000")
    """
    return f"{qty:,}"


def seconds_to_hms(seconds: float) -> str:
    """Convert seconds to human-readable HH:MM:SS format.
    
    Args:
        seconds: Number of seconds
        
    Returns:
        Formatted string (e.g., "01:30:45")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_trading_day_number(date: Optional[datetime] = None) -> int:
    """Get the trading day number (1-252 approx per year).
    
    Args:
        date: Optional date to check. Defaults to today.
        
    Returns:
        Day number within year (skipping weekends)
    """
    if date is None:
        date = now_market()
    elif date.tzinfo is None:
        date = UTC_TZ.localize(date).astimezone(MARKET_TZ)
    else:
        date = date.astimezone(MARKET_TZ)
    
    # Start of year
    year_start = datetime(date.year, 1, 1, tzinfo=MARKET_TZ)
    
    # Count trading days from start of year to date
    trading_days = 0
    current = year_start
    while current <= date:
        if current.weekday() < 5:  # Monday-Friday
            trading_days += 1
        current += timedelta(days=1)
    
    return trading_days


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max.
    
    Args:
        value: Value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Clamped value
    """
    return max(min_val, min(value, max_val))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero.
    
    Args:
        numerator: Numerator
        denominator: Denominator
        default: Value to return if denominator is zero
        
    Returns:
        Result of division or default
    """
    if denominator == 0:
        return default
    return numerator / denominator
