"""Risk manager for Breakout Trading Bot.

Implements position sizing and risk checks for breakout signals.
"""

import math
from typing import Dict, Any


def evaluate(account: Dict[str, Any], signal: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate whether a trade should be taken and how many shares to size.

    Args:
        account: Alpaca account info containing equity, buying_power, cash, etc.
        signal: Breakout signal dict with action, entry_level, stop_level, target_level.
        config: Risk config values:
            - max_risk_pct: Maximum equity risk per trade (default 0.01)
            - max_trades_per_day: Maximum trades allowed per day (default 3)
            - max_open_risk_pct: Maximum total open risk as fraction of equity (default 0.03)
            - min_shares: Minimum shares required to place a trade (default 1)
            - max_position_pct: Maximum position notional as fraction of equity (default 0.05)
            - current_trades_today: Number of trades already taken today (default 0)
            - current_open_risk: Current open risk dollars (default 0.0)
    Returns:
        Dict with keys: allowed, shares, reason, risk_per_share, max_risk_dollars, risk_dollars.
    """
    # Default config values
    max_risk_pct = config.get("max_risk_pct", 0.01)
    max_trades_per_day = config.get("max_trades_per_day", 3)
    max_open_risk_pct = config.get("max_open_risk_pct", 0.03)
    max_position_pct = config.get("max_position_pct", 0.05)
    min_shares = config.get("min_shares", 1)
    current_trades_today = config.get("current_trades_today", 0)
    current_open_risk = config.get("current_open_risk", 0.0)

    # Validate signal
    if not signal or signal.get("action") != "BUY":
        return {
            "allowed": False,
            "shares": 0,
            "reason": "No BUY signal",
        }

    entry_price = signal.get("entry_level")
    stop_price = signal.get("stop_level")
    target_price = signal.get("target_level")

    if entry_price is None or stop_price is None:
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Missing entry or stop level",
        }

    try:
        entry_price = float(entry_price)
        stop_price = float(stop_price)
    except (TypeError, ValueError):
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Invalid entry or stop price",
        }

    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Stop loss must be below entry price",
        }

    equity = float(account.get("equity", account.get("portfolio_value", 0.0) or 0.0))
    buying_power = float(account.get("buying_power", account.get("cash", 0.0) or 0.0))

    if equity <= 0:
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Account equity unavailable",
        }

    if current_trades_today >= max_trades_per_day:
        return {
            "allowed": False,
            "shares": 0,
            "reason": f"Max trades per day reached ({current_trades_today}/{max_trades_per_day})",
        }

    max_risk_dollars = equity * max_risk_pct
    shares = math.floor(max_risk_dollars / risk_per_share)

    if shares < min_shares:
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Trade size below minimum shares",
        }

    position_notional = entry_price * shares
    if position_notional > equity * max_position_pct:
        max_position_notional = equity * max_position_pct
        shares = math.floor(max_position_notional / entry_price)
        if shares < min_shares:
            return {
                "allowed": False,
                "shares": 0,
                "reason": "Position would exceed maximum notional size",
            }

    if entry_price * shares > buying_power:
        shares = math.floor(buying_power / entry_price)
        if shares < min_shares:
            return {
                "allowed": False,
                "shares": 0,
                "reason": "Insufficient buying power",
            }

    projected_open_risk = current_open_risk + (shares * risk_per_share)
    if projected_open_risk > equity * max_open_risk_pct:
        return {
            "allowed": False,
            "shares": 0,
            "reason": "Open risk would exceed allowed maximum",
        }

    return {
        "allowed": True,
        "shares": shares,
        "reason": "Allowed",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "risk_per_share": round(risk_per_share, 4),
        "max_risk_dollars": round(max_risk_dollars, 2),
        "risk_dollars": round(shares * risk_per_share, 2),
        "current_trades_today": current_trades_today,
        "current_open_risk": round(current_open_risk, 2),
    }
