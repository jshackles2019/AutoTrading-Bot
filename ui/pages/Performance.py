"""Performance analytics page for historical trade visualization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
DATA_TRADES = ROOT / "data" / "trades"


@st.cache_data(ttl=300)
def _load_trade_history() -> pd.DataFrame:
    """Load and normalize all trade CSV files under data/trades."""
    if not DATA_TRADES.exists():
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for csv_path in sorted(DATA_TRADES.glob("trades_*.csv")):
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue
        if df.empty:
            continue
        df["source_file"] = csv_path.name
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    if "timestamp" in combined.columns:
        combined["timestamp"] = pd.to_datetime(combined["timestamp"], errors="coerce", utc=True)
        combined["timestamp_local"] = combined["timestamp"].dt.tz_convert("America/New_York")
        combined["trade_date"] = combined["timestamp_local"].dt.date
        combined["trade_month"] = combined["timestamp_local"].dt.to_period("M").astype(str)

    if "trade_date" not in combined.columns:
        combined["trade_date"] = pd.NaT
    if "trade_month" not in combined.columns:
        combined["trade_month"] = pd.NA

    missing_date = combined["trade_date"].isna() if "trade_date" in combined.columns else pd.Series([True] * len(combined))
    if missing_date.any() and "source_file" in combined.columns:
        extracted = combined.loc[missing_date, "source_file"].astype(str).str.extract(r"(\d{8})", expand=False)
        parsed = pd.to_datetime(extracted, format="%Y%m%d", errors="coerce")
        combined.loc[missing_date, "trade_date"] = parsed.dt.date
        combined.loc[missing_date, "trade_month"] = parsed.dt.to_period("M").astype(str)

    numeric_cols = [
        "entry_price",
        "stop_loss",
        "take_profit",
        "shares",
        "filled_price",
        "filled_qty",
        "exit_price",
        "pnl",
        "pnl_pct",
    ]
    for col in numeric_cols:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    if "symbol" in combined.columns:
        combined["symbol"] = combined["symbol"].astype(str).str.upper().str.strip()

    if "pnl" not in combined.columns:
        combined["pnl"] = pd.NA

    # Fallback P&L estimate when explicit pnl is missing.
    if {"entry_price", "exit_price", "shares"}.issubset(combined.columns):
        missing_mask = combined["pnl"].isna()
        estimated = (combined["exit_price"] - combined["entry_price"]) * combined["shares"]
        combined.loc[missing_mask, "pnl"] = estimated[missing_mask]

    combined["pnl"] = pd.to_numeric(combined["pnl"], errors="coerce").fillna(0.0)
    combined["cum_pnl"] = combined["pnl"].cumsum()
    combined["win"] = combined["pnl"] > 0

    return combined


def _filter_trades(
    df: pd.DataFrame,
    start_date,
    end_date,
    months: list[str],
    symbols: list[str],
    sides: list[str],
) -> pd.DataFrame:
    """Apply user-selected filters to trade history."""
    filtered = df.copy()

    if "trade_date" in filtered.columns:
        filtered = filtered[(filtered["trade_date"] >= start_date) & (filtered["trade_date"] <= end_date)]

    if months and "trade_month" in filtered.columns:
        filtered = filtered[filtered["trade_month"].isin(months)]

    if symbols and "symbol" in filtered.columns:
        filtered = filtered[filtered["symbol"].isin(symbols)]

    if sides and "side" in filtered.columns:
        filtered = filtered[filtered["side"].isin(sides)]

    filtered = filtered.sort_values(by="timestamp", ascending=True)
    filtered["cum_pnl"] = filtered["pnl"].cumsum()
    return filtered


def _metric_row(df: pd.DataFrame) -> None:
    """Render top-level performance summary metrics."""
    total_trades = int(len(df))
    total_pnl = float(df["pnl"].sum()) if "pnl" in df.columns else 0.0
    avg_pnl = float(df["pnl"].mean()) if total_trades else 0.0
    win_rate = float((df["pnl"] > 0).mean() * 100.0) if total_trades else 0.0
    best_symbol = "N/A"

    if total_trades and "symbol" in df.columns:
        symbol_rank = (
            df.groupby("symbol", as_index=False)["pnl"]
            .sum()
            .sort_values(by="pnl", ascending=False)
        )
        if not symbol_rank.empty:
            best_symbol = str(symbol_rank.iloc[0]["symbol"])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Trades", total_trades)
    c2.metric("Total P/L", f"${total_pnl:,.2f}")
    c3.metric("Average P/L", f"${avg_pnl:,.2f}")
    c4.metric("Win rate", f"{win_rate:.1f}%")
    c5.metric("Top symbol", best_symbol)


def _chart_cumulative_pnl(df: pd.DataFrame) -> None:
    if df.empty or "timestamp_local" not in df.columns:
        st.info("No timestamped trades available for cumulative P/L chart.")
        return

    chart = (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X("timestamp_local:T", title="Time"),
            y=alt.Y("cum_pnl:Q", title="Cumulative P/L ($)"),
            tooltip=[
                alt.Tooltip("timestamp_local:T", title="Timestamp"),
                alt.Tooltip("symbol:N", title="Symbol"),
                alt.Tooltip("pnl:Q", title="Trade P/L", format=",.2f"),
                alt.Tooltip("cum_pnl:Q", title="Cumulative P/L", format=",.2f"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, width="stretch")


def _chart_monthly_pnl(df: pd.DataFrame) -> None:
    if df.empty or "trade_month" not in df.columns:
        st.info("No monthly trade data available.")
        return

    monthly = (
        df.groupby("trade_month", as_index=False)["pnl"]
        .sum()
        .sort_values(by="trade_month")
    )

    bars = (
        alt.Chart(monthly)
        .mark_bar()
        .encode(
            x=alt.X("trade_month:N", title="Month", sort=list(monthly["trade_month"])),
            y=alt.Y("pnl:Q", title="Monthly P/L ($)"),
            color=alt.condition("datum.pnl >= 0", alt.value("#19b37d"), alt.value("#ef476f")),
            tooltip=[
                alt.Tooltip("trade_month:N", title="Month"),
                alt.Tooltip("pnl:Q", title="P/L", format=",.2f"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(bars, width="stretch")


def _chart_symbol_pnl(df: pd.DataFrame) -> None:
    if df.empty or "symbol" not in df.columns:
        st.info("No symbol-level trade data available.")
        return

    per_symbol = (
        df.groupby("symbol", as_index=False)
        .agg(total_pnl=("pnl", "sum"), trades=("symbol", "count"))
        .sort_values(by="total_pnl", ascending=False)
    )

    chart = (
        alt.Chart(per_symbol)
        .mark_bar()
        .encode(
            y=alt.Y("symbol:N", sort="-x", title="Symbol"),
            x=alt.X("total_pnl:Q", title="Total P/L ($)"),
            color=alt.condition("datum.total_pnl >= 0", alt.value("#2ec4b6"), alt.value("#ff6b6b")),
            tooltip=[
                alt.Tooltip("symbol:N", title="Symbol"),
                alt.Tooltip("trades:Q", title="Trades"),
                alt.Tooltip("total_pnl:Q", title="Total P/L", format=",.2f"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart(chart, width="stretch")


def _summary_tables(df: pd.DataFrame, sort_by: str, ascending: bool) -> None:
    if df.empty:
        st.info("No trades match current filters.")
        return

    st.markdown("#### Symbol summary")
    if "symbol" in df.columns:
        symbol_summary = (
            df.groupby("symbol", as_index=False)
            .agg(
                trades=("symbol", "count"),
                total_pnl=("pnl", "sum"),
                avg_pnl=("pnl", "mean"),
                wins=("win", "sum"),
            )
            .sort_values(by=sort_by if sort_by in {"symbol", "trades", "total_pnl", "avg_pnl", "wins"} else "total_pnl", ascending=ascending)
        )
        symbol_summary["win_rate_pct"] = (symbol_summary["wins"] / symbol_summary["trades"]) * 100.0
        st.dataframe(symbol_summary, width="stretch")
    else:
        st.info("Symbol column is not present in trade history.")

    st.markdown("#### Trade records")
    display_cols = [
        "timestamp_local",
        "trade_month",
        "symbol",
        "side",
        "shares",
        "entry_price",
        "exit_price",
        "pnl",
        "pnl_pct",
        "status",
        "source_file",
    ]
    display_cols = [col for col in display_cols if col in df.columns]
    st.dataframe(df[display_cols], width="stretch")


st.set_page_config(page_title="Performance", page_icon="bar_chart", layout="wide")
st.title(":material/monitoring: Performance")
st.caption("Analyze historical trade results by month, symbol, and side with interactive charts.")

trades_df = _load_trade_history()
if trades_df.empty:
    st.info("No historical trades found under data/trades. Run sessions first to populate performance charts.")
    st.stop()

min_date = trades_df["trade_date"].min() if "trade_date" in trades_df.columns else None
max_date = trades_df["trade_date"].max() if "trade_date" in trades_df.columns else None

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([1.1, 1.1, 1.4, 1.1])
with filter_col1:
    start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
with filter_col2:
    end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)
with filter_col3:
    month_options = sorted(trades_df.get("trade_month", pd.Series(dtype=str)).dropna().unique().tolist())
    selected_months = st.multiselect("Months", options=month_options, default=month_options)
with filter_col4:
    side_options = sorted(trades_df.get("side", pd.Series(dtype=str)).dropna().astype(str).str.lower().unique().tolist())
    selected_sides = st.multiselect("Sides", options=side_options, default=side_options)

symbol_options = sorted(trades_df.get("symbol", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
selected_symbols = st.multiselect("Symbols", options=symbol_options, default=symbol_options)

if start_date > end_date:
    st.error("Start date cannot be after end date.")
    st.stop()

filtered_df = _filter_trades(
    trades_df,
    start_date=start_date,
    end_date=end_date,
    months=selected_months,
    symbols=selected_symbols,
    sides=selected_sides,
)

if filtered_df.empty:
    st.warning("No trades match the selected filters.")
    st.stop()

_metric_row(filtered_df)

left, right = st.columns(2)
with left:
    st.markdown("#### Cumulative P/L over time")
    _chart_cumulative_pnl(filtered_df)
with right:
    st.markdown("#### Monthly P/L")
    _chart_monthly_pnl(filtered_df)

st.markdown("#### P/L by symbol")
_chart_symbol_pnl(filtered_df)

sort_col1, sort_col2 = st.columns([1.2, 1.0])
with sort_col1:
    sort_by = st.selectbox("Sort symbol summary by", options=["total_pnl", "trades", "avg_pnl", "wins", "symbol"], index=0)
with sort_col2:
    sort_direction = st.selectbox("Sort direction", options=["descending", "ascending"], index=0)

_summary_tables(filtered_df, sort_by=sort_by, ascending=sort_direction == "ascending")
