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
AUTO_TRADER_PRESETS_FILE = DATA_UI / "auto_trader_presets.json"
WATCHDOG_STATE_FILE = DATA_UI / "watchdog_state.json"
WATCHDOG_LOG_FILE = DATA_LOGS / "watchdog_runner.log"
RUNTIME_STATUS_FILE = DATA_UI / "runtime_status.json"
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


def _load_watchdog_state() -> Optional[dict]:
    if not WATCHDOG_STATE_FILE.exists():
        return None
    try:
        return json.loads(WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_runtime_status() -> Optional[dict]:
    if not RUNTIME_STATUS_FILE.exists():
        return None
    try:
        return json.loads(RUNTIME_STATUS_FILE.read_text(encoding="utf-8"))
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


def _build_auto_trader_args(
    *,
    dry_run: bool,
    max_symbols: int,
    scan_selection: str,
    top_candidates: int,
    min_average_volume: int,
    risk_max_trades_per_day: int,
    risk_max_risk_pct: float,
    risk_max_open_risk_pct: float,
    risk_max_position_pct: float,
    risk_max_open_positions: int,
    risk_symbol_cooldown_minutes: float,
    risk_max_daily_drawdown_pct: float,
    risk_max_consecutive_losses: int,
) -> list[str]:
    """Build guarded continuous-scan args for one-click auto trader mode."""
    args = [
        "--symbol-universe",
        "us-all",
        "--max-symbols",
        str(int(max_symbols)),
        "--scan-selection",
        str(scan_selection),
        "--top-candidates",
        str(int(top_candidates)),
        "--min-average-volume",
        str(int(min_average_volume)),
        "--risk-max-trades-per-day",
        str(int(risk_max_trades_per_day)),
        "--risk-max-risk-pct",
        str(float(risk_max_risk_pct)),
        "--risk-max-open-risk-pct",
        str(float(risk_max_open_risk_pct)),
        "--risk-max-position-pct",
        str(float(risk_max_position_pct)),
        "--risk-max-open-positions",
        str(int(risk_max_open_positions)),
        "--risk-symbol-cooldown-minutes",
        str(float(risk_symbol_cooldown_minutes)),
        "--risk-max-daily-drawdown-pct",
        str(float(risk_max_daily_drawdown_pct)),
        "--risk-max-consecutive-losses",
        str(int(risk_max_consecutive_losses)),
    ]
    if dry_run:
        args.append("--dry-run")
    return args


def _default_auto_trader_presets() -> dict[str, dict[str, float | int | str]]:
    """Provide built-in guarded presets for auto-trader settings."""
    return {
        "conservative": {
            "max_symbols": 300,
            "scan_selection": "rotating",
            "top_candidates": 15,
            "min_average_volume": 250000,
            "risk_max_trades_per_day": 1,
            "risk_max_risk_pct": 0.003,
            "risk_max_open_risk_pct": 0.008,
            "risk_max_position_pct": 0.02,
            "risk_max_open_positions": 3,
            "risk_symbol_cooldown_minutes": 45,
            "risk_max_daily_drawdown_pct": 0.02,
            "risk_max_consecutive_losses": 2,
        },
        "balanced": {
            "max_symbols": 500,
            "scan_selection": "rotating",
            "top_candidates": 25,
            "min_average_volume": 100000,
            "risk_max_trades_per_day": 2,
            "risk_max_risk_pct": 0.005,
            "risk_max_open_risk_pct": 0.01,
            "risk_max_position_pct": 0.03,
            "risk_max_open_positions": 5,
            "risk_symbol_cooldown_minutes": 30,
            "risk_max_daily_drawdown_pct": 0.03,
            "risk_max_consecutive_losses": 3,
        },
        "aggressive": {
            "max_symbols": 900,
            "scan_selection": "rotating",
            "top_candidates": 40,
            "min_average_volume": 50000,
            "risk_max_trades_per_day": 4,
            "risk_max_risk_pct": 0.008,
            "risk_max_open_risk_pct": 0.02,
            "risk_max_position_pct": 0.05,
            "risk_max_open_positions": 8,
            "risk_symbol_cooldown_minutes": 20,
            "risk_max_daily_drawdown_pct": 0.05,
            "risk_max_consecutive_losses": 4,
        },
    }


def _load_auto_trader_presets() -> dict[str, dict[str, float | int | str]]:
    """Load preset file and merge with built-in defaults."""
    presets = _default_auto_trader_presets()
    if not AUTO_TRADER_PRESETS_FILE.exists():
        return presets
    try:
        loaded = json.loads(AUTO_TRADER_PRESETS_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for name, values in loaded.items():
                if isinstance(name, str) and isinstance(values, dict):
                    presets[name] = values
    except Exception:
        return presets
    return presets


def _save_auto_trader_presets(presets: dict[str, dict[str, float | int | str]]) -> None:
    """Persist preset dictionary to disk."""
    DATA_UI.mkdir(parents=True, exist_ok=True)
    AUTO_TRADER_PRESETS_FILE.write_text(json.dumps(presets, indent=2), encoding="utf-8")


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
            - **One-shot breaker overrides**: apply temporary breaker thresholds to a single one-shot run.
            - **Start Auto Trader (Guarded)**: launches continuous US-market scanning with stricter risk limits.
            - **Auto breaker guardrails**: halt trading after drawdown/loss streak limits and enforce symbol cooldowns.
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
        value=False,
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

    with st.expander("One-shot breaker overrides", expanded=False):
        apply_one_shot_breakers = st.toggle(
            "Apply one-shot breaker overrides",
            value=False,
            help="When enabled, one-shot run uses these breaker thresholds instead of config defaults.",
        )
        ob1, ob2 = st.columns(2)
        with ob1:
            one_shot_risk_max_open_positions = st.number_input(
                "One-shot max open positions",
                min_value=0,
                max_value=100,
                value=5,
                step=1,
                help="Maximum simultaneous positions allowed for this one-shot run.",
            )
            one_shot_risk_symbol_cooldown_minutes = st.number_input(
                "One-shot symbol cooldown (minutes)",
                min_value=0.0,
                max_value=1440.0,
                value=30.0,
                step=1.0,
                help="Cooldown window before re-entering the same symbol.",
            )
        with ob2:
            one_shot_risk_max_daily_drawdown_pct = st.number_input(
                "One-shot max daily drawdown",
                min_value=0.0,
                max_value=0.5,
                value=0.03,
                step=0.005,
                format="%.3f",
                help="Halt threshold as drawdown from session start equity.",
            )
            one_shot_risk_max_consecutive_losses = st.number_input(
                "One-shot max consecutive losses",
                min_value=0,
                max_value=50,
                value=3,
                step=1,
                help="Halt threshold for consecutive losing exits.",
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
        if apply_one_shot_breakers:
            run_args.extend(["--risk-max-open-positions", str(int(one_shot_risk_max_open_positions))])
            run_args.extend(["--risk-symbol-cooldown-minutes", str(float(one_shot_risk_symbol_cooldown_minutes))])
            run_args.extend(["--risk-max-daily-drawdown-pct", str(float(one_shot_risk_max_daily_drawdown_pct))])
            run_args.extend(["--risk-max-consecutive-losses", str(int(one_shot_risk_max_consecutive_losses))])
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

    st.caption("Auto trader quick start")
    auto_col1, auto_col2 = st.columns(2)
    with auto_col1:
        auto_trader_dry_run = st.toggle(
            "Auto trader dry run",
            value=True,
            help="Run continuous guarded scanning without placing live orders.",
        )
    with auto_col2:
        start_auto_bg_clicked = st.button("Start Auto Trader (Guarded)", use_container_width=True)

    presets = _load_auto_trader_presets()
    preset_names = sorted(presets.keys())
    if "auto_preset_selected" not in st.session_state or st.session_state["auto_preset_selected"] not in preset_names:
        st.session_state["auto_preset_selected"] = "balanced" if "balanced" in preset_names else preset_names[0]

    preset_col1, preset_col2 = st.columns([1.3, 1.0])
    with preset_col1:
        selected_preset_name = st.selectbox(
            "Auto preset",
            options=preset_names,
            key="auto_preset_selected",
            help="Load or overwrite guardrail settings using named presets.",
        )
    with preset_col2:
        load_preset_clicked = st.button("Load Preset", use_container_width=True)

    save_col1, save_col2, save_col3 = st.columns([1.2, 1.0, 1.0])
    with save_col1:
        preset_name_input = st.text_input(
            "Preset name",
            value=selected_preset_name,
            key="auto_preset_name_input",
            help="Name used when saving current guardrails as a preset.",
        )
    with save_col2:
        save_preset_clicked = st.button("Save Preset", use_container_width=True)
    with save_col3:
        delete_preset_clicked = st.button("Delete Preset", use_container_width=True)

    with st.expander("Auto trader guardrails", expanded=False):
        ag1, ag2 = st.columns(2)
        with ag1:
            auto_max_symbols = st.number_input(
                "Auto max symbols",
                min_value=25,
                max_value=5000,
                value=500,
                step=25,
                key="auto_max_symbols",
                help="How many symbols are scanned per loop in guarded auto mode.",
            )
            auto_scan_selection = st.selectbox(
                "Auto scan selection",
                options=["rotating", "random", "first"],
                index=0,
                key="auto_scan_selection",
                help="How symbols are chosen when max symbols caps the US universe.",
            )
            auto_top_candidates = st.number_input(
                "Auto top candidates",
                min_value=1,
                max_value=500,
                value=25,
                step=1,
                key="auto_top_candidates",
                help="Number of ranked symbols evaluated for potential entries each loop.",
            )
            auto_min_avg_volume = st.number_input(
                "Auto min average volume",
                min_value=0,
                max_value=100000000,
                value=100000,
                step=10000,
                key="auto_min_avg_volume",
                help="Liquidity floor for guarded auto mode.",
            )
        with ag2:
            auto_risk_max_trades_per_day = st.number_input(
                "Auto max trades/day",
                min_value=1,
                max_value=50,
                value=2,
                step=1,
                key="auto_risk_max_trades_per_day",
                help="Maximum trades allowed per day in guarded auto mode.",
            )
            auto_risk_max_risk_pct = st.number_input(
                "Auto max risk/trade",
                min_value=0.001,
                max_value=0.05,
                value=0.005,
                step=0.001,
                format="%.3f",
                key="auto_risk_max_risk_pct",
                help="Fraction of equity risked per trade.",
            )
            auto_risk_max_open_risk_pct = st.number_input(
                "Auto max open risk",
                min_value=0.002,
                max_value=0.2,
                value=0.01,
                step=0.001,
                format="%.3f",
                key="auto_risk_max_open_risk_pct",
                help="Maximum total open risk as a fraction of equity.",
            )
            auto_risk_max_position_pct = st.number_input(
                "Auto max position size",
                min_value=0.005,
                max_value=0.5,
                value=0.03,
                step=0.005,
                format="%.3f",
                key="auto_risk_max_position_pct",
                help="Maximum position notional as a fraction of equity.",
            )
            auto_risk_max_open_positions = st.number_input(
                "Auto max open positions",
                min_value=0,
                max_value=100,
                value=5,
                step=1,
                key="auto_risk_max_open_positions",
                help="Maximum simultaneous positions before new entries are blocked.",
            )
            auto_risk_symbol_cooldown_minutes = st.number_input(
                "Auto symbol cooldown (minutes)",
                min_value=0.0,
                max_value=1440.0,
                value=30.0,
                step=1.0,
                key="auto_risk_symbol_cooldown_minutes",
                help="Wait time before re-entering a symbol after an exit.",
            )
            auto_risk_max_daily_drawdown_pct = st.number_input(
                "Auto max daily drawdown",
                min_value=0.0,
                max_value=0.5,
                value=0.03,
                step=0.005,
                format="%.3f",
                key="auto_risk_max_daily_drawdown_pct",
                help="Session halt threshold as fraction drawdown from starting equity.",
            )
            auto_risk_max_consecutive_losses = st.number_input(
                "Auto max consecutive losses",
                min_value=0,
                max_value=50,
                value=3,
                step=1,
                key="auto_risk_max_consecutive_losses",
                help="Session halt threshold for losing exits in a row.",
            )

    if load_preset_clicked:
        preset = presets.get(selected_preset_name)
        if not preset:
            st.error("Selected preset was not found.")
        else:
            st.session_state["auto_max_symbols"] = int(preset.get("max_symbols", 500))
            st.session_state["auto_scan_selection"] = str(preset.get("scan_selection", "rotating"))
            st.session_state["auto_top_candidates"] = int(preset.get("top_candidates", 25))
            st.session_state["auto_min_avg_volume"] = int(preset.get("min_average_volume", 100000))
            st.session_state["auto_risk_max_trades_per_day"] = int(preset.get("risk_max_trades_per_day", 2))
            st.session_state["auto_risk_max_risk_pct"] = float(preset.get("risk_max_risk_pct", 0.005))
            st.session_state["auto_risk_max_open_risk_pct"] = float(preset.get("risk_max_open_risk_pct", 0.01))
            st.session_state["auto_risk_max_position_pct"] = float(preset.get("risk_max_position_pct", 0.03))
            st.session_state["auto_risk_max_open_positions"] = int(preset.get("risk_max_open_positions", 5))
            st.session_state["auto_risk_symbol_cooldown_minutes"] = float(preset.get("risk_symbol_cooldown_minutes", 30))
            st.session_state["auto_risk_max_daily_drawdown_pct"] = float(preset.get("risk_max_daily_drawdown_pct", 0.03))
            st.session_state["auto_risk_max_consecutive_losses"] = int(preset.get("risk_max_consecutive_losses", 3))
            st.success(f"Loaded preset: {selected_preset_name}")
            st.rerun()

    if save_preset_clicked:
        name = (preset_name_input or "").strip().lower()
        if not name:
            st.error("Preset name is required.")
        else:
            presets[name] = {
                "max_symbols": int(auto_max_symbols),
                "scan_selection": str(auto_scan_selection),
                "top_candidates": int(auto_top_candidates),
                "min_average_volume": int(auto_min_avg_volume),
                "risk_max_trades_per_day": int(auto_risk_max_trades_per_day),
                "risk_max_risk_pct": float(auto_risk_max_risk_pct),
                "risk_max_open_risk_pct": float(auto_risk_max_open_risk_pct),
                "risk_max_position_pct": float(auto_risk_max_position_pct),
                "risk_max_open_positions": int(auto_risk_max_open_positions),
                "risk_symbol_cooldown_minutes": float(auto_risk_symbol_cooldown_minutes),
                "risk_max_daily_drawdown_pct": float(auto_risk_max_daily_drawdown_pct),
                "risk_max_consecutive_losses": int(auto_risk_max_consecutive_losses),
            }
            _save_auto_trader_presets(presets)
            st.session_state["auto_preset_selected"] = name
            st.success(f"Saved preset: {name}")
            st.rerun()

    if delete_preset_clicked:
        name = selected_preset_name
        if name in {"conservative", "balanced", "aggressive"}:
            st.error("Built-in presets cannot be deleted.")
        elif name not in presets:
            st.error("Preset not found.")
        else:
            del presets[name]
            _save_auto_trader_presets(presets)
            remaining_names = sorted(presets.keys())
            st.session_state["auto_preset_selected"] = "balanced" if "balanced" in remaining_names else remaining_names[0]
            st.success(f"Deleted preset: {name}")
            st.rerun()

    auto_live_confirm_token = ""
    if live_guard_required and not auto_trader_dry_run:
        auto_live_confirm_token = st.text_input(
            "Live auto-trader confirmation token",
            placeholder="LIVE-TRADE-YES",
            help="Required to start guarded auto trader in live non-dry-run mode.",
        )

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

    if start_auto_bg_clicked:
        if _is_bg_running():
            st.warning("Background process is already running.")
        elif live_guard_required and not auto_trader_dry_run and auto_live_confirm_token != "LIVE-TRADE-YES":
            st.error("Live auto trader blocked. Enter token LIVE-TRADE-YES to proceed.")
        else:
            _clear_scan_stop()
            auto_args = _build_auto_trader_args(
                dry_run=auto_trader_dry_run,
                max_symbols=int(auto_max_symbols),
                scan_selection=auto_scan_selection,
                top_candidates=int(auto_top_candidates),
                min_average_volume=int(auto_min_avg_volume),
                risk_max_trades_per_day=int(auto_risk_max_trades_per_day),
                risk_max_risk_pct=float(auto_risk_max_risk_pct),
                risk_max_open_risk_pct=float(auto_risk_max_open_risk_pct),
                risk_max_position_pct=float(auto_risk_max_position_pct),
                risk_max_open_positions=int(auto_risk_max_open_positions),
                risk_symbol_cooldown_minutes=float(auto_risk_symbol_cooldown_minutes),
                risk_max_daily_drawdown_pct=float(auto_risk_max_daily_drawdown_pct),
                risk_max_consecutive_losses=int(auto_risk_max_consecutive_losses),
            )
            state = _start_background(auto_args, env_overrides=env_overrides)
            state["account_mode"] = account_mode
            state["mode"] = "auto_trader_guarded"
            _save_bg_state(state)
            st.success(f"Guarded auto trader started (PID {state['pid']}).")

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

    watchdog_state = _load_watchdog_state()
    if watchdog_state:
        st.caption("Watchdog Supervisor")
        st.write(f"Watchdog status: **{watchdog_state.get('status', 'unknown')}**")
        st.write(f"Watchdog restarts: `{watchdog_state.get('restart_count', 0)}`")
        if watchdog_state.get("last_exit_code") is not None:
            st.write(f"Watchdog last exit code: `{watchdog_state.get('last_exit_code')}`")
        if watchdog_state.get("next_restart_at"):
            st.write(f"Watchdog next restart: `{watchdog_state.get('next_restart_at')}`")
        if watchdog_state.get("message"):
            st.write(f"Watchdog note: {watchdog_state.get('message')}")
        if WATCHDOG_LOG_FILE.exists():
            st.text_area(
                "watchdog-log",
                _read_last_lines(WATCHDOG_LOG_FILE, max_lines=60, newest_first=True),
                height=130,
            )

    runtime_status = _load_runtime_status()
    if runtime_status:
        st.caption("Runtime Circuit Breakers")
        st.write(f"Runtime status: **{runtime_status.get('status', 'unknown')}**")
        if runtime_status.get("halt_reason"):
            st.error(f"Halt reason: {runtime_status.get('halt_reason')}")
        if runtime_status.get("message"):
            st.write(f"Runtime note: {runtime_status.get('message')}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Consecutive Losses", int(runtime_status.get("consecutive_losses", 0)))
        c2.metric("Active Positions", int(runtime_status.get("active_positions", 0)))
        c3.metric("Session P/L", f"${float(runtime_status.get('session_pnl', 0.0)):,.2f}")

        breakers = runtime_status.get("circuit_breakers", {}) or {}
        st.write(
            "Configured breakers | "
            f"drawdown: {breakers.get('max_daily_drawdown_pct', 'N/A')} | "
            f"consecutive losses: {breakers.get('max_consecutive_losses', 'N/A')} | "
            f"max open positions: {breakers.get('max_open_positions', 'N/A')} | "
            f"cooldown min: {breakers.get('symbol_cooldown_minutes', 'N/A')}"
        )

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
