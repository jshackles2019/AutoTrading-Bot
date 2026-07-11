"""Executor for Breakout Trading Bot.

This module provides a thin execution layer between strategy/risk logic and the
Alpaca client. It is designed to be testable without a live Alpaca connection.
"""

from typing import Dict, Any, Optional


DEFAULT_ORDER_TYPE = "market"
DEFAULT_TIME_IN_FORCE = "day"


def build_order_payload(
    symbol: str,
    qty: int,
    side: str = "buy",
    order_type: str = DEFAULT_ORDER_TYPE,
    time_in_force: str = DEFAULT_TIME_IN_FORCE,
    limit_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a normalized Alpaca order payload."""
    if side.lower() not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")

    order_type = order_type.lower()
    if order_type not in {"market", "limit"}:
        raise ValueError("order_type must be 'market' or 'limit'")

    if order_type == "limit" and limit_price is None:
        raise ValueError("limit_price must be provided for limit orders")

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "qty": int(qty),
        "side": side.lower(),
        "type": order_type,
        "time_in_force": time_in_force.lower(),
    }

    if limit_price is not None:
        payload["limit_price"] = float(limit_price)

    if stop_loss is not None:
        payload["stop_loss"] = float(stop_loss)

    if take_profit is not None:
        payload["take_profit"] = float(take_profit)

    if extra:
        payload.update(extra)

    return payload


def _default_client():
    """Lazy-load the default Alpaca client implementation."""
    try:
        from src import alpaca_client
    except ImportError:
        import alpaca_client
    return alpaca_client


def _default_logger():
    """Lazy-load the default logger instance."""
    try:
        from src.logger import get_logger
    except ImportError:
        from logger import get_logger
    return get_logger()


def submit_order(
    order_params: Dict[str, Any],
    client: Optional[Any] = None,
    logger: Optional[Any] = None,
    use_bracket: bool = False,
) -> Dict[str, Any]:
    """Submit an order through the executor.

    Args:
        order_params: Normalized order parameters.
        client: Optional Alpaca client-like object with submit_order().
        logger: Optional logger with log_order() and log_error().
        use_bracket: Whether to attempt bracket order placement.

    Returns:
        Order details returned by the client.
    """
    client = client or _default_client()
    logger = logger or _default_logger()

    if use_bracket and (order_params.get("stop_loss") is not None or order_params.get("take_profit") is not None):
        if hasattr(client, "submit_bracket_order"):
            try:
                order = client.submit_bracket_order(order_params)
            except Exception as exc:
                if logger:
                    logger.log_error(f"Bracket order failed, falling back to single order: {exc}", exc)
                order = client.submit_order(order_params)
        else:
            if logger:
                logger.log_error(
                    "Bracket order requested but client does not support submit_bracket_order; submitting a normal order instead."
                )
            order = client.submit_order(order_params)
    else:
        order = client.submit_order(order_params)

    if logger:
        try:
            logger.log_order(order)
        except Exception as exc:
            logger.log_error(f"Failed to log order: {exc}", exc)

    return order


def close_position(
    symbol: str,
    qty: Optional[int] = None,
    client: Optional[Any] = None,
    logger: Optional[Any] = None,
) -> Dict[str, Any]:
    """Close an open position or reduce it.

    Args:
        symbol: Symbol to close.
        qty: Shares to close. None closes the whole position if supported.
        client: Optional Alpaca client-like object with close_position() or submit_order().
        logger: Optional logger with log_order() and log_error().
    """
    client = client or _default_client()
    logger = logger or _default_logger()

    if hasattr(client, "close_position"):
        order = client.close_position(symbol, qty)
    else:
        order = client.submit_order({
            "symbol": symbol,
            "qty": qty,
            "side": "sell",
            "type": "market",
            "time_in_force": DEFAULT_TIME_IN_FORCE,
        })

    if logger:
        try:
            logger.log_order(order)
        except Exception as exc:
            logger.log_error(f"Failed to log close position order: {exc}", exc)

    return order
