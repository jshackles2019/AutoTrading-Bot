"""Risk manager (stub).

Implement evaluate(account, signal, config) to return:
{ "allowed": True/False, "shares": N, "reason": "..." }
"""
import math


def evaluate(account, signal, config):
    # TODO: implement position sizing and risk checks
    return {"allowed": False, "shares": 0, "reason": "stub"}
