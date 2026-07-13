"""Streamlit UI for the Breakout Trading Bot.

This dashboard provides a simple control panel for smoke tests and dry-run execution,
plus visibility into logs and trades written by the existing bot logger.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
DATA_LOGS = ROOT / "data" / "logs"
DATA_TRADES = ROOT / "data" / "trades"
DATA_UI = ROOT / "data" / "ui"
BG_STATE_FILE = DATA_UI / "background_runner.json"
BG_OUTPUT_FILE = DATA_LOGS / "background_runner.log"
SCANNER_SNAPSHOT_FILE = DATA_UI / "scanner_snapshot.json"
STOP_SCANS_FLAG_FILE = DATA_UI / "stop_scans.flag"
SRC_MAIN = ROOT / "src" / "main.py"
REPO_PROCESS_HELPER = ROOT / "scripts" / "repo_processes.ps1"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


st.set_page_config(
    page_title="Breakout Bot Console",
    page_icon="chart_with_upwards_trend",
    layout="wide",
)


def _latest_file(folder: Path, pattern: str) -> Optional[Path]:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _read_last_lines(path: Path, max_lines: int = 200, newest_first: bool = False) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-max_lines:]
    if newest_first:
        tail = list(reversed(tail))
    return "\n".join(tail)


def _run_python(args: list[str], env_overrides: Optional[dict[str, str]] = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    process = subprocess.run(
        [sys.executable, str(SRC_MAIN), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    return process.returncode, process.stdout, process.stderr


def _save_bg_state(state: dict) -> None:
    DATA_UI.mkdir(parents=True, exist_ok=True)
    BG_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _load_bg_state() -> Optional[dict]:
    if not BG_STATE_FILE.exists():
        return None
    try:
        return json.loads(BG_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _clear_bg_state() -> None:
    if BG_STATE_FILE.exists():
        BG_STATE_FILE.unlink()


def _set_scan_stop() -> None:
    DATA_UI.mkdir(parents=True, exist_ok=True)
    STOP_SCANS_FLAG_FILE.write_text(
        datetime.now().isoformat(timespec="seconds"),
        encoding="utf-8",
    )


def _clear_scan_stop() -> None:
    if STOP_SCANS_FLAG_FILE.exists():
        STOP_SCANS_FLAG_FILE.unlink()


def _scan_stop_requested() -> bool:
    return STOP_SCANS_FLAG_FILE.exists()


def _clear_application_logs() -> tuple[int, int]:
    """Truncate log files so the UI/log directory does not grow indefinitely."""
    DATA_LOGS.mkdir(parents=True, exist_ok=True)
    truncated = 0
    failed = 0
    for log_path in DATA_LOGS.glob("*.log"):
        try:
            log_path.write_text("", encoding="utf-8")
            truncated += 1
        except Exception:
            failed += 1
    return truncated, failed


def _run_repo_process_helper(action: str) -> tuple[int, str, str]:
    if not REPO_PROCESS_HELPER.exists():
        return 1, "", f"Missing helper script: {REPO_PROCESS_HELPER}"

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(REPO_PROCESS_HELPER),
        action,
    ]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    # tasklist is reliable on Windows for checking running processes by PID.
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return "No tasks are running" not in result.stdout


def _start_background(args: list[str], env_overrides: Optional[dict[str, str]] = None) -> dict:
    DATA_LOGS.mkdir(parents=True, exist_ok=True)
    DATA_UI.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    command = [sys.executable, str(SRC_MAIN), *args]
    with open(BG_OUTPUT_FILE, "a", encoding="utf-8") as output:
        output.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] START {' '.join(command)}\n")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

        proc = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            creationflags=creationflags,
            env=env,
        )

    state = {
        "pid": proc.pid,
        "command": "python src/main.py " + " ".join(args),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "output_file": str(BG_OUTPUT_FILE),
    }
    _save_bg_state(state)
    return state


def _is_bg_running() -> bool:
    state = _load_bg_state()
    if not state:
        return False
    pid = int(state.get("pid", -1))
    running = _pid_running(pid)
    if not running:
        _clear_bg_state()
    return running


def _bg_status() -> tuple[str, Optional[dict]]:
    state = _load_bg_state()
    if not state:
        return "Stopped", None
    pid = int(state.get("pid", -1))
    if _pid_running(pid):
        return "Running", state
    _clear_bg_state()
    return "Stopped", None


def _stop_background() -> bool:
    state = _load_bg_state()
    if not state:
        return False
    pid = int(state.get("pid", -1))
    if pid <= 0:
        _clear_bg_state()
        return False

    result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
    _clear_bg_state()
    return result.returncode == 0


def _load_trades_df() -> pd.DataFrame:
    latest = _latest_file(DATA_TRADES, "trades_*.csv")
    if not latest:
        return pd.DataFrame()
    try:
        return pd.read_csv(latest)
    except Exception:
        return pd.DataFrame()


def _load_scanner_snapshot() -> Optional[dict]:
    if not SCANNER_SNAPSHOT_FILE.exists():
        return None
    try:
        return json.loads(SCANNER_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _account_keys_present() -> bool:
    return bool(os.getenv("ALPACA_KEY_ID") and os.getenv("ALPACA_SECRET_KEY"))


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
        account = alpaca_client.get_account()
        return account, None
    except Exception as exc:
        return None, str(exc)


def _format_status(value: object) -> str:
    text = str(value) if value is not None else "Unavailable"
    if "." in text:
        text = text.split(".")[-1]
    text = text.replace("_", " ").strip().title()
    return text or "Unavailable"


st.title("Breakout Trading Bot")
st.caption("Control dry-runs, run smoke tests, and inspect logs/trades in one place.")

refresh_col1, refresh_col2 = st.columns([1.2, 1.0])
with refresh_col1:
    auto_refresh = st.toggle("Auto-refresh dashboard", value=True)
with refresh_col2:
    refresh_seconds = st.slider("Refresh every (seconds)", min_value=2, max_value=30, value=5)

refresh_every = f"{refresh_seconds}s" if auto_refresh else None

left, right = st.columns([1.2, 2.0])

with left:
    st.subheader("Controls")
    with st.expander("Control Definitions", expanded=False):
        st.markdown(
            """
            - **Account mode**: `paper` uses simulated trading, `live` uses real-money account actions.
            - **Skip market check**: allows runs outside regular market hours.
            - **Dry run mode**: simulates strategy decisions without placing broker orders.
            - **Smoke test only**: runs a minimal connectivity/config check then exits.
            - **Symbol universe**: choose symbols from config only, or scan all tradeable US symbols.
            - **Max symbols**: cap how many symbols are evaluated in each loop.
            - **Selection mode**: choose how capped symbols are sampled (rotate, random, or fixed-first).
            - **Top ranked candidates**: limit how many scored symbols are considered for signals.
            - **Price and volume filters**: drop illiquid or out-of-range symbols before scoring.
            - **Score weights**: tune the scoring influence of confidence, breakout strength, volume, and momentum.
            - **Volume ratio cap**: prevent very large volume spikes from dominating the score.
            - **Additional symbols**: manually include symbols for targeted testing.
            - **Use max loops / Max loops**: stop automatically after a chosen number of loops.
            """
        )
    if "account_mode" not in st.session_state:
        st.session_state["account_mode"] = _default_account_mode()

    account_mode = st.selectbox(
        "Account mode",
        options=["paper", "live"],
        index=0 if st.session_state["account_mode"] == "paper" else 1,
        key="account_mode",
        help="Select which Alpaca account mode to use for this run.",
    )

    env_overrides = {"ALPACA_PAPER": "True" if account_mode == "paper" else "False"}

    if account_mode == "live":
        st.warning("Live mode selected. This can place real trades when dry-run is disabled.")

    live_guard_required = account_mode == "live"

    skip_market_check = st.toggle(
        "Skip market check",
        value=True,
        help="Run even if the market appears closed. Useful for tests and diagnostics.",
    )
    dry_run = st.toggle(
        "Dry run mode",
        value=True,
        help="Simulate strategy execution without sending real orders to Alpaca.",
    )
    smoke_test = st.toggle(
        "Smoke test only",
        value=False,
        help="Run a quick health check (config/API/basic flow) and exit.",
    )

    st.markdown("**Symbols**")
    symbol_universe = st.selectbox(
        "Symbol universe",
        options=["config", "us-all"],
        help="Use configured symbols or all active tradeable US equities.",
    )
    max_symbols = st.number_input(
        "Max symbols to scan per loop (0 = unlimited)",
        min_value=0,
        max_value=10000,
        value=200,
        step=1,
        help="Maximum symbols evaluated in each scan loop. Set 0 for no cap.",
    )
    scan_selection = st.selectbox(
        "Capped-scan symbol selection",
        options=["rotating", "random", "first"],
        help="When max symbols is capped, rotate through the universe, pick random symbols, or always use the first slice.",
    )
    top_candidates = st.number_input(
        "Top ranked candidates",
        min_value=1,
        max_value=1000,
        value=20,
        step=1,
        help="Number of highest-scoring symbols passed to signal evaluation.",
    )
    min_price = st.number_input(
        "Min price filter",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help="Exclude symbols below this price. Set 0 to disable.",
    )
    max_price = st.number_input(
        "Max price filter (0 to disable)",
        min_value=0.0,
        value=0.0,
        step=1.0,
        help="Exclude symbols above this price. Set 0 to disable.",
    )
    min_avg_volume = st.number_input(
        "Min average volume (20 bars)",
        min_value=0,
        value=0,
        step=10000,
        help="Require at least this 20-bar average volume. Set 0 to disable.",
    )
    st.markdown("**Scanner score weights**")
    weight_confidence = st.number_input(
        "Weight: confidence",
        min_value=0.0,
        value=50.0,
        step=1.0,
        help="How much strategy confidence contributes to ranking score.",
    )
    weight_breakout = st.number_input(
        "Weight: breakout",
        min_value=0.0,
        value=200.0,
        step=1.0,
        help="How strongly breakout distance from key levels influences score.",
    )
    weight_volume = st.number_input(
        "Weight: volume",
        min_value=0.0,
        value=10.0,
        step=1.0,
        help="How much unusual volume boosts symbol ranking.",
    )
    weight_momentum = st.number_input(
        "Weight: momentum",
        min_value=0.0,
        value=100.0,
        step=1.0,
        help="How much short-term price momentum affects ranking.",
    )
    volume_ratio_cap = st.number_input(
        "Volume ratio cap",
        min_value=0.1,
        value=5.0,
        step=0.1,
        help="Upper bound on volume-ratio effect so spikes do not dominate scoring.",
    )
    symbol_input = st.text_input(
        "Additional/override symbols (comma-separated)",
        placeholder="AAPL,MSFT,NVDA",
        help="Comma-separated symbols to target directly (for testing or focus lists).",
    )
    append_symbols = st.toggle(
        "Append typed symbols instead of replacing",
        value=True,
        help="On: add typed symbols to the selected universe. Off: use only typed symbols.",
    )

    live_confirm_token = ""
    if live_guard_required and not dry_run and not smoke_test:
        st.error("Live non-dry-run mode requires explicit confirmation token.")
        live_confirm_token = st.text_input(
            "Type confirmation token to enable live trading",
            placeholder="LIVE-TRADE-YES",
            help="Required for live runs when dry-run is disabled.",
        )

    max_loops_enabled = st.toggle(
        "Use max loops",
        value=True,
        help="Automatically stop after N loops instead of running indefinitely.",
    )
    max_loops = st.number_input(
        "Max loops",
        min_value=1,
        max_value=1000,
        value=1,
        step=1,
        help="Loop count used when max loops is enabled.",
    )

    run_args: list[str] = []
    if smoke_test:
        run_args.append("--smoke-test")
    else:
        if dry_run:
            run_args.append("--dry-run")
        if skip_market_check:
            run_args.append("--skip-market-check")
        if max_loops_enabled:
            run_args.extend(["--max-loops", str(int(max_loops))])
        run_args.extend(["--top-candidates", str(int(top_candidates))])
        run_args.extend(["--weight-confidence", str(float(weight_confidence))])
        run_args.extend(["--weight-breakout", str(float(weight_breakout))])
        run_args.extend(["--weight-volume", str(float(weight_volume))])
        run_args.extend(["--weight-momentum", str(float(weight_momentum))])
        run_args.extend(["--volume-ratio-cap", str(float(volume_ratio_cap))])
        if symbol_universe != "config":
            run_args.extend(["--symbol-universe", symbol_universe, "--max-symbols", str(int(max_symbols))])
            run_args.extend(["--scan-selection", scan_selection])
        if min_price > 0:
            run_args.extend(["--min-price", str(float(min_price))])
        if max_price > 0:
            run_args.extend(["--max-price", str(float(max_price))])
        if int(min_avg_volume) > 0:
            run_args.extend(["--min-average-volume", str(int(min_avg_volume))])
        if symbol_input.strip():
            run_args.extend(["--symbols", symbol_input.strip()])
            if append_symbols:
                run_args.append("--append-symbols")

    st.code("python src/main.py " + " ".join(run_args), language="bash")

    run_col, smoke_col = st.columns(2)
    with run_col:
        run_clicked = st.button("Run One-Shot", type="primary", use_container_width=True)
    with smoke_col:
        smoke_clicked = st.button("Run Smoke Test", use_container_width=True)

    if smoke_clicked:
        rc, out, err = _run_python(["--smoke-test"], env_overrides=env_overrides)
        st.session_state["last_run"] = {
            "when": datetime.now().isoformat(timespec="seconds"),
            "cmd": "python src/main.py --smoke-test",
            "rc": rc,
            "out": out,
            "err": err,
        }

    if run_clicked:
        if live_guard_required and not dry_run and not smoke_test and live_confirm_token != "LIVE-TRADE-YES":
            st.error("Live trading blocked. Enter token LIVE-TRADE-YES to proceed.")
        else:
            _clear_scan_stop()
            rc, out, err = _run_python(run_args, env_overrides=env_overrides)
            st.session_state["last_run"] = {
                "when": datetime.now().isoformat(timespec="seconds"),
                "cmd": "python src/main.py " + " ".join(run_args),
                "rc": rc,
                "out": out,
                "err": err,
            }

    st.divider()
    st.subheader("Background Runner")
    st.caption("Persistent runner: survives Streamlit refresh/restart. Output streams into log files.")

    bg_status, bg_state = _bg_status()
    st.write(f"Status: **{bg_status}**")
    if bg_state and bg_state.get("started_at"):
        st.write(f"Started: `{bg_state['started_at']}`")
    if bg_state and bg_state.get("pid"):
        st.write(f"PID: `{bg_state['pid']}`")
    if bg_state and bg_state.get("command"):
        st.write(f"Command: `{bg_state['command']}`")
    st.write(f"Scan stop requested: {'Yes' if _scan_stop_requested() else 'No'}")

    start_col, stop_col, req_stop_col, clear_stop_col = st.columns(4)
    with start_col:
        start_bg_clicked = st.button("Start Background", use_container_width=True)
    with stop_col:
        stop_bg_clicked = st.button("Stop Background", use_container_width=True)
    with req_stop_col:
        request_scan_stop_clicked = st.button("Request Scan Stop", use_container_width=True)
    with clear_stop_col:
        clear_scan_stop_clicked = st.button("Clear Stop", use_container_width=True)

    if request_scan_stop_clicked:
        _set_scan_stop()
        stopped = _stop_background()
        if stopped:
            st.success("Stop requested and background process terminated.")
        else:
            st.info("Stop requested. Active scanning process will stop on its next check.")

    if clear_scan_stop_clicked:
        _clear_scan_stop()
        st.success("Manual stop flag cleared.")

    clear_logs_confirm = st.checkbox(
        "Confirm clear log files",
        value=False,
        help="Truncates all .log files under data/logs.",
    )
    clear_logs_clicked = st.button("Clear Logs", use_container_width=True)
    if clear_logs_clicked:
        if not clear_logs_confirm:
            st.warning("Enable confirmation before clearing log files.")
        else:
            truncated, failed = _clear_application_logs()
            st.session_state.pop("last_run", None)
            if failed == 0:
                st.success(f"Cleared {truncated} log file(s).")
            else:
                st.warning(f"Cleared {truncated} log file(s), failed on {failed} file(s).")

    st.caption("Rogue process tools")
    proc_list_col, proc_kill_col = st.columns(2)
    with proc_list_col:
        list_rogue_clicked = st.button("List Rogue Processes", use_container_width=True)
    with proc_kill_col:
        kill_rogue_clicked = st.button("Kill Rogue Processes", use_container_width=True)

    if list_rogue_clicked:
        rc, out, err = _run_repo_process_helper("-List")
        st.session_state["process_tool_output"] = {
            "action": "List",
            "rc": rc,
            "out": out,
            "err": err,
        }

    if kill_rogue_clicked:
        rc, out, err = _run_repo_process_helper("-Kill")
        st.session_state["process_tool_output"] = {
            "action": "Kill",
            "rc": rc,
            "out": out,
            "err": err,
        }

    process_tool_output = st.session_state.get("process_tool_output")
    if process_tool_output:
        rc_color = "green" if process_tool_output.get("rc", 1) == 0 else "red"
        st.markdown(
            f"**Process tool:** {process_tool_output.get('action', 'Unknown')}  \n"
            f"**Exit code:** :{rc_color}[{process_tool_output.get('rc', 'N/A')}]"
        )
        if process_tool_output.get("out"):
            st.text_area("process-tool-stdout", process_tool_output["out"], height=120)
        if process_tool_output.get("err"):
            st.text_area("process-tool-stderr", process_tool_output["err"], height=100)

    if start_bg_clicked:
        if _is_bg_running():
            st.warning("Background process is already running.")
        elif live_guard_required and not dry_run and not smoke_test and live_confirm_token != "LIVE-TRADE-YES":
            st.error("Live background run blocked. Enter token LIVE-TRADE-YES to proceed.")
        else:
            _clear_scan_stop()
            state = _start_background(run_args, env_overrides=env_overrides)
            state["account_mode"] = account_mode
            _save_bg_state(state)
            st.success(f"Background bot process started (PID {state['pid']}).")

    if stop_bg_clicked:
        stopped = _stop_background()
        if stopped:
            st.success("Background bot process stopped.")
        else:
            st.info("No active background process found.")

    st.divider()
    st.subheader("Environment")
    st.write(f"Python: `{sys.executable}`")
    st.write(f"Root: `{ROOT}`")
    st.write(f"Alpaca keys present: {'Yes' if _account_keys_present() else 'No'}")

    st.divider()
    st.subheader("Explore Stock")
    st.caption("Manual orders and stock overview were moved to the Explore Stock page in the sidebar.")

with right:
    @st.fragment(run_every=refresh_every)
    def _live_panels() -> None:
        st.subheader("Account Snapshot")
        account, account_err = _account_snapshot(account_mode)
        card1, card2, card3 = st.columns(3)
        if account:
            card1.metric("Equity", f"${account.get('equity', 0):,.2f}")
            card2.metric("Buying Power", f"${account.get('buying_power', 0):,.2f}")
            card3.metric("Status", _format_status(account.get("status", "Unavailable")))
        else:
            card1.metric("Equity", "N/A")
            card2.metric("Buying Power", "N/A")
            card3.metric("Status", "Unavailable")
            if account_err:
                st.warning(f"Account fetch failed: {account_err}")

        st.subheader("Run Output")
        last_run = st.session_state.get("last_run")
        if last_run:
            rc_color = "green" if last_run["rc"] == 0 else "red"
            st.markdown(
                f"**Last run:** {last_run['when']}  \\n"
                f"**Command:** `{last_run['cmd']}`  \\n"
                f"**Exit code:** :{rc_color}[{last_run['rc']}]"
            )
            if last_run["out"]:
                st.text_area("stdout", last_run["out"], height=220)
            if last_run["err"]:
                st.text_area("stderr", last_run["err"], height=160)
        else:
            st.info("No run yet. Use the controls to start a run.")

        st.subheader("Recent Log Tail")
        latest_log = _latest_file(DATA_LOGS, "bot_*.log")
        if latest_log:
            st.caption(f"File: `{latest_log.name}`")
            st.text_area("log", _read_last_lines(latest_log, max_lines=120, newest_first=True), height=260)
        else:
            st.info("No bot logs found yet.")

        st.subheader("Background Runner Log")
        if BG_OUTPUT_FILE.exists():
            st.caption(f"File: `{BG_OUTPUT_FILE.name}`")
            st.text_area(
                "background-log",
                _read_last_lines(BG_OUTPUT_FILE, max_lines=120, newest_first=True),
                height=220,
            )
        else:
            st.info("No background runner log found yet.")

        st.subheader("Recent Trades")
        trades_df = _load_trades_df()
        if trades_df.empty:
            st.info("No trade rows found yet.")
        else:
            st.dataframe(trades_df.tail(30), use_container_width=True)

        st.subheader("Scanner Snapshot")
        snapshot = _load_scanner_snapshot()
        if snapshot:
            st.caption(f"Updated: {snapshot.get('timestamp', 'N/A')}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Scanned", int(snapshot.get("scanned", 0)))
            m2.metric("Buy Signals", int(snapshot.get("buy_signals", 0)))
            m3.metric("Selected", int(snapshot.get("selected", 0)))
            m4.metric("Top Analyzed", int(len(snapshot.get("top_analyzed", []))))

            top_rows = snapshot.get("top", [])
            if top_rows:
                st.dataframe(pd.DataFrame(top_rows), use_container_width=True)
            else:
                analyzed_rows = snapshot.get("top_analyzed", [])
                if analyzed_rows:
                    st.info("No BUY candidates in latest snapshot. Showing top analyzed symbols.")
                    st.dataframe(pd.DataFrame(analyzed_rows), use_container_width=True)
                else:
                    st.info("No ranked candidates in latest snapshot.")
        else:
            st.info("No scanner snapshot found yet.")

    _live_panels()

st.divider()
st.caption("Tip: start with Dry run + Skip market check + Max loops=1 for fast verification.")
