"""Dedicated stock exploration page: manual orders and symbol overview."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _default_account_mode() -> str:
    is_paper = os.getenv("ALPACA_PAPER", "True").strip().lower() == "true"
    return "paper" if is_paper else "live"


def _account_keys_present() -> bool:
    return bool(os.getenv("ALPACA_KEY_ID") and os.getenv("ALPACA_SECRET_KEY"))


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


@st.cache_data(ttl=900)
def _search_symbols_cached(account_mode: str, query: str, limit: int = 60) -> list[str]:
    alpaca_client = _get_alpaca_client(account_mode)
    symbols = alpaca_client.get_tradeable_us_symbols(max_symbols=None)
    q = (query or "").strip().upper()
    if not q:
        return symbols[:limit]
    matched = [s for s in symbols if q in s]
    return matched[:limit]


st.set_page_config(page_title="Explore Stock", page_icon="mag", layout="wide")
st.title("Explore Stock")
st.caption("Place manual orders and inspect symbol-level market context.")

if "account_mode" not in st.session_state:
    st.session_state["account_mode"] = _default_account_mode()

header_left, header_right = st.columns([2, 1])
with header_left:
    account_mode = st.selectbox(
        "Account mode",
        options=["paper", "live"],
        index=0 if st.session_state["account_mode"] == "paper" else 1,
        key="account_mode",
        help="Actions and data on this page use the selected account mode.",
    )
with header_right:
    st.write(f"Alpaca keys present: {'Yes' if _account_keys_present() else 'No'}")

st.divider()
st.subheader("Manual Order Ticket")
st.caption("Place one-off buy/sell orders from the dashboard.")

manual_symbol = st.text_input("Symbol", value="AAPL", key="explore_manual_symbol").strip().upper()
col_side, col_type, col_size_mode = st.columns(3)
with col_side:
    manual_side = st.selectbox("Side", options=["buy", "sell"], key="explore_manual_side")
with col_type:
    manual_type = st.selectbox("Order type", options=["market", "limit"], key="explore_manual_type")
with col_size_mode:
    manual_size_mode = st.selectbox("Order size", options=["shares", "dollars"], key="explore_manual_size_mode")

manual_qty = None
manual_notional = None
if manual_size_mode == "shares":
    manual_qty = st.number_input(
        "Quantity",
        min_value=1,
        max_value=1000000,
        value=1,
        step=1,
        key="explore_manual_qty",
    )
else:
    st.caption("Dollar sizing uses Alpaca notional market orders for fractional-capable assets.")
    manual_notional = st.number_input(
        "Dollar amount",
        min_value=1.0,
        max_value=10000000.0,
        value=100.0,
        step=1.0,
        key="explore_manual_notional",
    )

manual_limit_price = None
if manual_type == "limit" and manual_size_mode == "shares":
    manual_limit_price = st.number_input(
        "Limit price",
        min_value=0.01,
        value=1.0,
        step=0.01,
        key="explore_manual_limit_price",
    )

live_order_confirmed = True
if account_mode == "live":
    live_order_confirmed = st.checkbox(
        "I understand this will place a live order.",
        value=False,
        key="explore_manual_live_order_confirmed",
    )

manual_submit = st.button("Submit Manual Order", use_container_width=True)

if manual_submit:
    if not _account_keys_present():
        st.error("Missing Alpaca API keys in environment.")
    elif account_mode == "live" and not live_order_confirmed:
        st.error("Live manual order blocked. Confirm the live-order checkbox first.")
    elif not manual_symbol:
        st.error("Symbol is required.")
    elif manual_size_mode == "dollars" and manual_side != "buy":
        st.error("Dollar-based notional sizing is enabled for buy orders only in this UI.")
    elif manual_size_mode == "dollars" and manual_type != "market":
        st.error("Dollar-based notional sizing requires market order type.")
    else:
        try:
            alpaca_client = _get_alpaca_client(account_mode)
            order_payload = {
                "symbol": manual_symbol,
                "side": manual_side,
                "type": manual_type,
                "time_in_force": "day",
            }
            if manual_size_mode == "shares":
                order_payload["qty"] = int(manual_qty)
            else:
                order_payload["notional"] = float(manual_notional)

            if manual_type == "limit" and manual_size_mode == "shares":
                order_payload["limit_price"] = float(manual_limit_price)

            order_result = alpaca_client.submit_order(order_payload)
            st.success("Order submitted.")
            st.json(order_result)
        except Exception as exc:
            st.error(f"Manual order failed: {exc}")

st.divider()
st.subheader("Stock Search And Overview")
search_query = st.text_input("Search ticker", placeholder="TSLA", key="explore_search_query")

symbol_options: list[str] = []
try:
    symbol_options = _search_symbols_cached(account_mode, search_query)
except Exception as exc:
    st.warning(f"Symbol search unavailable: {exc}")

selected_symbol = None
if symbol_options:
    selected_symbol = st.selectbox("Matching symbols", options=symbol_options, key="explore_selected_symbol")
elif search_query.strip():
    st.info("No symbols matched your search.")

if selected_symbol:
    try:
        alpaca_client = _get_alpaca_client(account_mode)
        overview = alpaca_client.get_symbol_overview(selected_symbol, lookback=60)

        c1, c2, c3 = st.columns(3)
        c1.metric("Last Close", f"${(overview.get('last_close') or 0):,.2f}")
        c2.metric("Day Change", f"${(overview.get('day_change') or 0):,.2f}")
        c3.metric("Day Change %", f"{(overview.get('day_change_pct') or 0):.2f}%")

        st.caption(
            f"{overview.get('name') or selected_symbol} | "
            f"Exchange: {overview.get('exchange') or 'N/A'} | "
            f"Status: {overview.get('status') or 'N/A'}"
        )
        st.write(
            f"Tradable: {overview.get('tradable')} | Shortable: {overview.get('shortable')} | "
            f"Marginable: {overview.get('marginable')} | Fractionable: {overview.get('fractionable')}"
        )
        if overview.get("avg_volume_20") is not None:
            st.write(f"20-day average volume: {overview.get('avg_volume_20'):,.0f}")

        bars = overview.get("bars", [])
        if bars:
            bars_df = pd.DataFrame(bars)
            bars_df["timestamp"] = pd.to_datetime(bars_df["timestamp"])
            st.line_chart(bars_df.set_index("timestamp")["close"], height=220)
            st.dataframe(bars_df.tail(20), use_container_width=True)
    except Exception as exc:
        st.error(f"Failed to load overview for {selected_symbol}: {exc}")
