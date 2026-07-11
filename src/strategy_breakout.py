"""Breakout strategy for Breakout Trading Bot.

Detects breakout signals using support/resistance levels, volume confirmation,
and optional volatility expansion.
"""

from typing import Dict, List, Any, Optional
import statistics


class BreakoutSignal:
    """Represents a breakout signal."""
    
    def __init__(self, symbol: str, action: str = "NONE", 
                 entry_level: Optional[float] = None,
                 stop_level: Optional[float] = None,
                 target_level: Optional[float] = None,
                 confidence: float = 0.0,
                 volume_check: bool = False,
                 volatility_check: bool = False):
        """Initialize a signal.
        
        Args:
            symbol: Stock symbol
            action: 'BUY', 'SELL', or 'NONE'
            entry_level: Entry price
            stop_level: Stop loss level
            target_level: Take profit level
            confidence: Signal confidence 0-1
            volume_check: Whether volume confirmed the signal
            volatility_check: Whether volatility expansion occurred
        """
        self.symbol = symbol
        self.action = action
        self.entry_level = entry_level
        self.stop_level = stop_level
        self.target_level = target_level
        self.confidence = confidence
        self.volume_check = volume_check
        self.volatility_check = volatility_check
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "action": self.action,
            "entry_level": self.entry_level,
            "stop_level": self.stop_level,
            "target_level": self.target_level,
            "confidence": self.confidence,
            "volume_check": self.volume_check,
            "volatility_check": self.volatility_check,
        }


def evaluate(bars: List[Dict[str, Any]], symbol: str, 
            config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Evaluate bars and generate breakout signal.
    
    Args:
        bars: List of OHLCV bars from alpaca_client.get_bars()
        symbol: Stock symbol
        config: Configuration dict with optional keys:
            - lookback_support: Bars to look back for support (default 20)
            - lookback_resistance: Bars to look back for resistance (default 20)
            - volume_threshold_factor: Volume multiplier (default 1.5)
            - atr_multiplier: ATR multiplier for stop loss (default 2.0)
            - target_multiplier: Risk-to-reward ratio (default 2.0)
            - check_volatility: Check for volatility expansion (default False)
            
    Returns:
        Signal dict with action, entry_level, stop_level, target_level, confidence, etc.
    """
    if not config:
        config = {}
    
    # Configuration with defaults
    lookback_support = config.get("lookback_support", 20)
    lookback_resistance = config.get("lookback_resistance", 20)
    volume_threshold_factor = config.get("volume_threshold_factor", 1.5)
    atr_multiplier = config.get("atr_multiplier", 2.0)
    target_multiplier = config.get("target_multiplier", 2.0)
    check_volatility = config.get("check_volatility", False)
    
    # Validate input
    if not bars or len(bars) < max(lookback_support, lookback_resistance):
        return BreakoutSignal(symbol, action="NONE").to_dict()
    
    # Extract price and volume data
    closes = [bar["close"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    volumes = [bar["volume"] for bar in bars]
    
    # Current bar (last bar)
    current_close = closes[-1]
    current_high = highs[-1]
    current_low = lows[-1]
    current_volume = volumes[-1]
    
    # Previous bar
    prev_close = closes[-2] if len(closes) > 1 else current_close
    
    # Calculate support and resistance
    support = _calculate_support(lows, lookback_support)
    resistance = _calculate_resistance(highs, lookback_resistance)
    
    # Check for breakout above resistance
    is_breakout = current_close > resistance and prev_close <= resistance
    
    # Check volume confirmation
    avg_volume = statistics.mean(volumes[:-1]) if len(volumes) > 1 else current_volume
    volume_confirmed = current_volume > avg_volume * volume_threshold_factor
    
    # Check volatility expansion (optional)
    volatility_expanded = False
    if check_volatility:
        volatility_expanded = _check_volatility_expansion(bars, atr_multiplier)
    
    # No signal if no breakout
    if not is_breakout:
        return BreakoutSignal(symbol, action="NONE").to_dict()
    
    # Calculate risk metrics
    entry_price = current_close
    stop_loss = support  # Stop below support
    risk_per_share = entry_price - stop_loss
    
    if risk_per_share <= 0:
        # Invalid trade setup
        return BreakoutSignal(symbol, action="NONE").to_dict()
    
    # Calculate target (take profit)
    target_price = entry_price + (risk_per_share * target_multiplier)
    
    # Calculate confidence
    confidence = _calculate_confidence(
        is_breakout,
        volume_confirmed,
        volatility_expanded,
        risk_per_share,
        entry_price
    )
    
    # Create signal
    signal = BreakoutSignal(
        symbol=symbol,
        action="BUY",
        entry_level=round(entry_price, 2),
        stop_level=round(stop_loss, 2),
        target_level=round(target_price, 2),
        confidence=round(confidence, 3),
        volume_check=volume_confirmed,
        volatility_check=volatility_expanded,
    )
    
    return signal.to_dict()


def _calculate_support(lows: List[float], lookback: int) -> float:
    """Calculate support level as the minimum low over lookback period."""
    if not lows or lookback <= 0:
        return lows[-1] if lows else 0.0
    
    lookback_data = lows[-lookback:]
    return min(lookback_data)


def _calculate_resistance(highs: List[float], lookback: int) -> float:
    """Calculate resistance level as the maximum high over lookback period."""
    if not highs or lookback <= 0:
        return highs[-1] if highs else 0.0
    
    lookback_data = highs[-lookback:]
    return max(lookback_data)


def _check_volatility_expansion(bars: List[Dict[str, Any]], atr_multiplier: float = 2.0) -> bool:
    """Check if current bar has volatility expansion.
    
    Compares current bar's range to average range over recent bars.
    """
    if len(bars) < 14:  # Need 14 bars for ATR calculation
        return False
    
    # Calculate ATR (Average True Range)
    true_ranges = []
    for i in range(len(bars) - 13, len(bars)):
        current_high = bars[i]["high"]
        current_low = bars[i]["low"]
        prev_close = bars[i - 1]["close"] if i > 0 else current_high
        
        tr = max(
            current_high - current_low,
            abs(current_high - prev_close),
            abs(current_low - prev_close)
        )
        true_ranges.append(tr)
    
    atr = statistics.mean(true_ranges)
    
    # Current bar's range
    current_range = bars[-1]["high"] - bars[-1]["low"]
    
    # Check if current range > ATR * multiplier
    return current_range > atr * atr_multiplier


def _calculate_confidence(is_breakout: bool, volume_confirmed: bool,
                         volatility_expanded: bool, risk_per_share: float,
                         entry_price: float) -> float:
    """Calculate signal confidence score (0-1).
    
    Confidence increases with:
    - Confirmed breakout
    - Volume confirmation
    - Volatility expansion
    - Better risk/reward ratio (lower risk per share relative to entry)
    """
    confidence = 0.0
    
    # Base: breakout detected (already filtered out if not)
    if is_breakout:
        confidence += 0.4
    
    # Volume confirmation adds weight
    if volume_confirmed:
        confidence += 0.3
    
    # Volatility expansion adds weight
    if volatility_expanded:
        confidence += 0.2
    
    # Risk-to-entry ratio (prefer smaller risk %)
    risk_pct = (risk_per_share / entry_price) * 100 if entry_price > 0 else 50
    if risk_pct < 1.0:
        confidence += 0.1
    elif risk_pct < 2.0:
        confidence += 0.05
    # else: no bonus for larger risk
    
    return min(confidence, 1.0)


# Legacy function for compatibility
def evaluate_legacy(bars: List[Dict[str, Any]], symbol: str) -> Dict[str, Any]:
    """Legacy wrapper for evaluate() using default config."""
    return evaluate(bars, symbol)
