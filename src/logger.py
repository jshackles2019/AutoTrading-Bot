"""Logger utilities (stub).

Implement logging of signals, orders, fills, and PnL to files in data/logs and data/trades.
"""
import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("trading_bot")
handler = logging.FileHandler(LOG_DIR / "bot.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_trade(signal, risk_decision, order):
    logger.info(f"TRADE {signal} {risk_decision} {order}")


def log_skip(symbol, reason=None):
    logger.info(f"SKIP {symbol} {reason}")


def log_no_signal(symbol):
    logger.info(f"NO_SIGNAL {symbol}")
