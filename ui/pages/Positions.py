"""Dedicated positions dashboard page for selected Alpaca account mode."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_account_mode() -> str:
    is_paper = os.getenv("ALPACA_PAPER", "True").strip().lower() == "true"
    return "paper" if is_paper else "live"


def _get_alpaca_client(account_mode: str):
    expected_paper = account_mode == "paper"
    os.environ["ALPACA_PAPER"] = "True" if expected_paper else "False"
    try:
        from src import alpaca_client
    except ImportError:
        import alpaca_client

    if getattr(alpaca_client, "ALPACA_PAPER", None) != expected_paper:
        alpaca_client = importlib.reload(alpaca_client)
    return alpaca_client


def _account_snapshot(account_mode: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        alpaca_client = _get_alpaca_client(account_mode)
        return alpaca_client.get_account(), None
    except Exception as exc:
        return None, str(exc)


def _positions_snapshot(account_mode: str) -> tuple[pd.DataFrame, Optional[str]]:
    try:
        alpaca_client = _get_alpaca_client(account_mode)
        positions = alpaca_client.get_open_positions()
        if not positions:
            return pd.DataFrame(), None
        df = pd.DataFrame(positions)
        numeric_cols = ["qty", "entry_price", "current_price", "market_value", "unrealized_pl", "unrealized_plpc"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df, None
    except Exception as exc:
        return pd.DataFrame(), str(exc)


def _format_status(value: object) -> str:
    text = str(value) if value is not None else "Unavailable"
    if "." in text:
        text = text.split(".")[-1]
    text = text.replace("_", " ").strip().title()
    return text or "Unavailable"


st.set_page_config(page_title="Positions", page_icon="bar_chart", layout="wide")
st.title("Positions Dashboard")
st.caption("View current open positions for the selected account mode.")

if "account_mode" not in st.session_state:
    st.session_state["account_mode"] = _default_account_mode()

top_left, top_right = st.columns([2, 1])
with top_left:
    account_mode = st.selectbox(
        "Account mode",
        options=["paper", "live"],
        index=0 if st.session_state["account_mode"] == "paper" else 1,
        key="account_mode",
        help="Positions are loaded from the selected account mode.",
    )
with top_right:
    refresh = st.button("Refresh Now", use_container_width=True)

if refresh:
    st.rerun()

account, account_err = _account_snapshot(account_mode)
if account_err:
    if account_mode == "live" and "not authorized" in account_err.lower():
        st.info(
            "Live account is not authorized with the current API keys. "
            "Use live keys for live mode, or switch back to paper mode."
        )
    else:
        st.warning(f"Account fetch failed: {account_err}")

metric1, metric2, metric3, metric4 = st.columns(4)
if account:
    metric1.metric("Mode", account_mode.upper())
    metric2.metric("Equity", f"${account.get('equity', 0):,.2f}")
    metric3.metric("Buying Power", f"${account.get('buying_power', 0):,.2f}")
    metric4.metric("Status", _format_status(account.get("status", "Unavailable")))
else:
    metric1.metric("Mode", account_mode.upper())
    metric2.metric("Equity", "N/A")
    metric3.metric("Buying Power", "N/A")
    metric4.metric("Status", "Unavailable")

positions_df, positions_err = _positions_snapshot(account_mode)
if positions_err:
    if account_mode == "live" and "not authorized" in positions_err.lower():
        st.info(
            "Live positions are unavailable because the current API keys are not authorized for live mode."
        )
    else:
        st.error(f"Positions fetch failed: {positions_err}")
elif positions_df.empty:
    st.info("No open positions for this account.")
else:
    total_mv = float(positions_df["market_value"].sum()) if "market_value" in positions_df.columns else 0.0
    total_upl = float(positions_df["unrealized_pl"].sum()) if "unrealized_pl" in positions_df.columns else 0.0
    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("Open Positions", int(len(positions_df)))
    stat2.metric("Total Market Value", f"${total_mv:,.2f}")
    stat3.metric("Total Unrealized P/L", f"${total_upl:,.2f}")

    if "unrealized_pl" in positions_df.columns:
        positions_df = positions_df.sort_values(by="unrealized_pl", ascending=False)
    st.dataframe(positions_df, use_container_width=True)
