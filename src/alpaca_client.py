"""Alpaca client wrapper (stub).

Implement get_account, get_bars, submit_order, get_open_positions here using alpaca-py.
"""

from dotenv import load_dotenv
import os

load_dotenv()

ALPACA_KEY = os.getenv("ALPACA_KEY_ID")
ALPACA_SECRET = os.getenv("ALPACA_SECRET_KEY")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "True")


def get_account():
    # TODO: integrate with alpaca-py to return account info
    return {"equity": 100000}


def get_bars(symbol, timeframe, lookback=50):
    # TODO: fetch OHLCV bars and return as a list/dict
    return []


def submit_order(order_params):
    # TODO: submit an order to Alpaca (paper) and return order details
    return {"status": "stub"}


def get_open_positions():
    return []
