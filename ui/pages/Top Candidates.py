"""Live top-ranked scanner candidates page."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
DATA_UI = ROOT / "data" / "ui"
SCANNER_SNAPSHOT_FILE = DATA_UI / "scanner_snapshot.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@st.cache_data(ttl=2)
def _load_scanner_snapshot() -> dict | None:
    if not SCANNER_SNAPSHOT_FILE.exists():
        return None
    try:
        return json.loads(SCANNER_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


st.set_page_config(page_title="Top Candidates", page_icon="bar_chart", layout="wide")
st.title("Top Ranked Candidates")
st.caption("Dynamically updated rankings from the scanner as symbols are analyzed.")

refresh_left, refresh_right = st.columns([2, 1])
with refresh_left:
    auto_refresh = st.toggle(
        "Auto-refresh",
        value=True,
        help="When enabled, this page refreshes automatically while scanner output updates.",
    )
with refresh_right:
    refresh_seconds = st.slider("Refresh every (seconds)", min_value=2, max_value=30, value=5)

if st.button("Refresh Now", use_container_width=True):
    st.rerun()

refresh_every = f"{refresh_seconds}s" if auto_refresh else None


@st.fragment(run_every=refresh_every)
def _render_candidates() -> None:
    snapshot = _load_scanner_snapshot()
    if not snapshot:
        st.info("No scanner snapshot found yet. Start a run from Home to generate rankings.")
        return

    st.caption(f"Last updated: {snapshot.get('timestamp', 'N/A')}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Scanned", int(snapshot.get("scanned", 0)))
    m2.metric("BUY Signals", int(snapshot.get("buy_signals", 0)))
    m3.metric("Selected BUY", int(snapshot.get("selected", 0)))
    analyzed_rows = snapshot.get("top_analyzed", [])
    m4.metric("Top Analyzed", int(len(analyzed_rows)))

    st.subheader("Top Analyzed Symbols")
    if analyzed_rows:
        analyzed_df = pd.DataFrame(analyzed_rows)
        if "score" in analyzed_df.columns:
            analyzed_df["score"] = pd.to_numeric(analyzed_df["score"], errors="coerce")
            analyzed_df = analyzed_df.sort_values(by="score", ascending=False)
        st.dataframe(analyzed_df, use_container_width=True)
    else:
        st.info("No analyzed candidate rows yet.")

    st.subheader("BUY Candidates")
    buy_rows = snapshot.get("top", [])
    if buy_rows:
        buy_df = pd.DataFrame(buy_rows)
        if "score" in buy_df.columns:
            buy_df["score"] = pd.to_numeric(buy_df["score"], errors="coerce")
            buy_df = buy_df.sort_values(by="score", ascending=False)
        st.dataframe(buy_df, use_container_width=True)
    else:
        st.info("No BUY candidates in the latest scan. Top analyzed symbols are shown above.")


_render_candidates()
