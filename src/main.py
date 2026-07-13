#!/usr/bin/env python3
"""Main entry point for Breakout Trading Bot.

Implements the core trading loop that monitors symbols, generates signals,
manages risk, and executes trades during market hours.
"""

import argparse
import json
import os
import random
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import statistics

try:
    from src import alpaca_client, utils
    from src.notifier import notify_discord
    from src.strategy_breakout import evaluate as evaluate_strategy
    from src.risk_manager import evaluate as evaluate_risk
    from src.executor import submit_order, close_position
    from src.logger import get_logger
except ImportError:
    import alpaca_client
    import utils
    from notifier import notify_discord
    from strategy_breakout import evaluate as evaluate_strategy
    from risk_manager import evaluate as evaluate_risk
    from executor import submit_order, close_position
    from logger import get_logger


DATA_UI_DIR = Path(__file__).resolve().parents[1] / "data" / "ui"
SCANNER_SNAPSHOT_PATH = DATA_UI_DIR / "scanner_snapshot.json"
STOP_SCANS_FLAG_PATH = DATA_UI_DIR / "stop_scans.flag"
ACTIVE_BOT_PROCESS_PATH = DATA_UI_DIR / "active_bot_process.json"
RUNTIME_STATUS_PATH = DATA_UI_DIR / "runtime_status.json"


def _write_active_bot_process_state() -> None:
    """Persist active bot PID so operators can detect/stop rogue runs."""
    try:
        DATA_UI_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "entry": str(Path(__file__).resolve()),
        }
        ACTIVE_BOT_PROCESS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def _clear_active_bot_process_state() -> None:
    """Remove active bot PID file when this process exits."""
    try:
        if not ACTIVE_BOT_PROCESS_PATH.exists():
            return
        payload = json.loads(ACTIVE_BOT_PROCESS_PATH.read_text(encoding="utf-8"))
        if int(payload.get("pid", -1)) == os.getpid():
            ACTIVE_BOT_PROCESS_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _parse_symbols(symbols_csv: Optional[str]) -> List[str]:
    """Parse comma-separated symbols and normalize to uppercase unique list."""
    if not symbols_csv:
        return []
    normalized: List[str] = []
    for token in symbols_csv.split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized


def _resolve_symbols(
    config: Dict[str, Any],
    symbol_universe: str,
    symbols_csv: Optional[str],
    append_symbols: bool,
) -> List[str]:
    """Resolve final symbol list from config, CLI overrides, and optional universe mode."""
    if symbol_universe == "us-all":
        # Pull the full active universe first; scan capping/selection happens later.
        base_symbols = alpaca_client.get_tradeable_us_symbols(max_symbols=None)
    else:
        base_symbols = list(config.get("symbols", []))

    cli_symbols = _parse_symbols(symbols_csv)
    if not cli_symbols:
        return base_symbols

    if append_symbols:
        seen = set(base_symbols)
        merged = list(base_symbols)
        for symbol in cli_symbols:
            if symbol not in seen:
                merged.append(symbol)
                seen.add(symbol)
        return merged

    return cli_symbols


def _resolve_scanner_config(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Resolve scanner configuration from settings + CLI overrides."""
    scanner = dict(config.get("scanner", {}))

    if args.top_candidates is not None:
        scanner["top_candidates"] = args.top_candidates
    if args.min_price is not None:
        scanner["min_price"] = args.min_price
    if args.max_price is not None:
        scanner["max_price"] = args.max_price
    if args.min_average_volume is not None:
        scanner["min_average_volume"] = args.min_average_volume
    if args.volume_ratio_cap is not None:
        scanner["volume_ratio_cap"] = args.volume_ratio_cap

    scanner.setdefault("top_candidates", 20)
    scanner.setdefault("min_price", None)
    scanner.setdefault("max_price", None)
    scanner.setdefault("min_average_volume", None)
    scanner.setdefault("volume_ratio_cap", 5.0)

    default_weights = {
        "confidence": 50.0,
        "breakout": 200.0,
        "volume": 10.0,
        "momentum": 100.0,
    }
    configured_weights = scanner.get("score_weights", {})
    if not isinstance(configured_weights, dict):
        configured_weights = {}
    weights = dict(default_weights)
    weights.update(configured_weights)
    if args.weight_confidence is not None:
        weights["confidence"] = args.weight_confidence
    if args.weight_breakout is not None:
        weights["breakout"] = args.weight_breakout
    if args.weight_volume is not None:
        weights["volume"] = args.weight_volume
    if args.weight_momentum is not None:
        weights["momentum"] = args.weight_momentum
    scanner["score_weights"] = weights

    scanner["max_symbols"] = args.max_symbols if args.max_symbols and args.max_symbols > 0 else None
    if args.scan_selection is not None:
        scanner["scan_selection"] = args.scan_selection

    scanner.setdefault("max_symbols", None)
    scanner.setdefault("scan_selection", "rotating")

    config["scanner"] = scanner
    return scanner


def _resolve_risk_config(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """Resolve risk configuration from settings + CLI overrides."""
    risk = dict(config.get("risk", {}))

    if args.risk_max_risk_pct is not None:
        risk["max_risk_pct"] = args.risk_max_risk_pct
    if args.risk_max_trades_per_day is not None:
        risk["max_trades_per_day"] = args.risk_max_trades_per_day
    if args.risk_max_open_risk_pct is not None:
        risk["max_open_risk_pct"] = args.risk_max_open_risk_pct
    if args.risk_max_position_pct is not None:
        risk["max_position_pct"] = args.risk_max_position_pct
    if args.risk_max_open_positions is not None:
        risk["max_open_positions"] = args.risk_max_open_positions
    if args.risk_symbol_cooldown_minutes is not None:
        risk["symbol_cooldown_minutes"] = args.risk_symbol_cooldown_minutes
    if args.risk_max_daily_drawdown_pct is not None:
        risk["max_daily_drawdown_pct"] = args.risk_max_daily_drawdown_pct
    if args.risk_max_consecutive_losses is not None:
        risk["max_consecutive_losses"] = args.risk_max_consecutive_losses

    risk.setdefault("max_risk_pct", 0.01)
    risk.setdefault("max_trades_per_day", 3)
    risk.setdefault("max_open_risk_pct", 0.03)
    risk.setdefault("max_position_pct", 0.05)
    risk.setdefault("max_open_positions", 5)
    risk.setdefault("symbol_cooldown_minutes", 30)
    risk.setdefault("max_daily_drawdown_pct", 0.03)
    risk.setdefault("max_consecutive_losses", 3)

    config["risk"] = risk
    return risk


class TradingSession:
    """Manages a single trading session."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        dry_run: bool = False,
        max_loops: Optional[int] = None,
        bypass_market_hours: bool = False,
    ):
        """Initialize trading session.
        
        Args:
            config: Configuration dictionary from settings.yaml
            dry_run: If True, simulate order execution without live order API calls
            max_loops: Optional limit for loop iterations (useful for deterministic testing)
            bypass_market_hours: If True, allow loop iterations even when market is closed
        """
        self.config = config
        self.dry_run = dry_run
        self.max_loops = max_loops if (max_loops is None or max_loops >= 1) else 1
        self.bypass_market_hours = bypass_market_hours
        self.logger = get_logger()
        
        # Trading state
        self.trades_today = 0
        self.open_risk_dollars = 0.0
        self.active_trades = {}  # symbol -> trade details
        self.session_start = datetime.now()
        self.session_pnl = 0.0
        self.trades_closed = 0
        self.wins = 0
        self.consecutive_losses = 0
        self.scan_cursor = 0
        self._rng = random.Random()
        self.symbol_cooldowns: Dict[str, float] = {}
        self.halt_reason: Optional[str] = None
        self.entry_lockout = False
        self.entry_lockout_reason: Optional[str] = None

        risk_cfg = self.config.get("risk", {})
        self.max_daily_drawdown_pct = risk_cfg.get("max_daily_drawdown_pct")
        self.max_consecutive_losses = risk_cfg.get("max_consecutive_losses")
        self.max_open_positions = risk_cfg.get("max_open_positions")
        self.symbol_cooldown_minutes = float(risk_cfg.get("symbol_cooldown_minutes", 0) or 0)
        self.session_start_equity: Optional[float] = None

        # Optional deterministic test hook for circuit-breaker automation tests.
        test_hooks = self.config.get("test_hooks", {}) if isinstance(self.config, dict) else {}
        self.force_halt_after_loops = test_hooks.get("force_halt_after_loops")
        self.force_halt_reason = str(test_hooks.get("force_halt_reason", "Forced halt test hook"))

        self._restore_runtime_context()

    def _restore_runtime_context(self) -> None:
        """Restore breaker-related runtime context so restarts preserve protections."""
        if not RUNTIME_STATUS_PATH.exists():
            return
        try:
            payload = json.loads(RUNTIME_STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return

        self.consecutive_losses = int(payload.get("consecutive_losses", self.consecutive_losses) or 0)
        self.session_start_equity = payload.get("session_start_equity", self.session_start_equity)
        self.entry_lockout = bool(payload.get("entry_lockout", False))
        self.entry_lockout_reason = payload.get("entry_lockout_reason")

        cooldowns = payload.get("symbol_cooldowns")
        if isinstance(cooldowns, dict):
            restored: Dict[str, float] = {}
            for symbol, ts in cooldowns.items():
                key = str(symbol).upper()
                try:
                    restored[key] = float(ts)
                except (TypeError, ValueError):
                    continue
            if restored:
                self.symbol_cooldowns = restored

    def _reset_runtime_context(self, clear_cooldowns: bool = False) -> None:
        """Reset persisted runtime breaker context, optionally clearing symbol cooldowns."""
        self.consecutive_losses = 0
        self.halt_reason = None
        self.entry_lockout = False
        self.entry_lockout_reason = None
        if clear_cooldowns:
            self.symbol_cooldowns = {}
        self._write_runtime_status("reset", "Runtime context reset")

    def _set_entry_lockout(self, reason: str) -> None:
        """Activate safe-mode lockout that blocks new entries until reset/reconciliation."""
        self.entry_lockout = True
        self.entry_lockout_reason = reason
        self.logger.logger.error(f"SAFE MODE LOCKOUT | {reason}")
        self._write_runtime_status("safe_mode_lockout", reason)
        notify_discord(
            "reconciliation_mismatch",
            reason,
            title="Breakout Bot Startup Reconciliation Mismatch",
        )

    def _perform_startup_reconciliation(self) -> None:
        """Reconcile broker positions against local tracked state before enabling entries."""
        try:
            broker_positions = alpaca_client.get_open_positions()
        except Exception as e:
            self._set_entry_lockout(f"Unable to reconcile broker positions at startup: {e}")
            return

        broker_symbols = {str(pos.get("symbol", "")).upper() for pos in broker_positions if pos.get("symbol")}
        local_symbols = {str(symbol).upper() for symbol in self.active_trades.keys()}

        if broker_symbols != local_symbols:
            self._set_entry_lockout(
                "Startup reconciliation mismatch detected. "
                f"Broker symbols={sorted(broker_symbols)} | "
                f"Local tracked symbols={sorted(local_symbols)}"
            )

    def _write_runtime_status(self, status: str, message: str, account_equity: Optional[float] = None) -> None:
        """Persist runtime/circuit-breaker status for the UI."""
        try:
            DATA_UI_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "safe_mode_lockout" if self.entry_lockout and status == "running" else status,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "message": message,
                "halt_reason": self.halt_reason,
                "entry_lockout": bool(self.entry_lockout),
                "entry_lockout_reason": self.entry_lockout_reason,
                "session_start": self.session_start.isoformat(timespec="seconds"),
                "session_start_equity": self.session_start_equity,
                "account_equity": account_equity,
                "session_pnl": round(float(self.session_pnl), 2),
                "consecutive_losses": int(self.consecutive_losses),
                "active_positions": int(len(self.active_trades)),
                "circuit_breakers": {
                    "max_daily_drawdown_pct": self.max_daily_drawdown_pct,
                    "max_consecutive_losses": self.max_consecutive_losses,
                    "max_open_positions": self.max_open_positions,
                    "symbol_cooldown_minutes": self.symbol_cooldown_minutes,
                },
                "symbol_cooldowns": self.symbol_cooldowns,
            }
            RUNTIME_STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _trigger_halt(self, reason: str, account_equity: Optional[float] = None) -> None:
        """Set halt reason and persist a halted runtime status record."""
        self.halt_reason = reason
        self.logger.logger.error(f"CIRCUIT BREAKER TRIGGERED | {reason}")
        self._write_runtime_status("halted", reason, account_equity=account_equity)
        notify_discord(
            "circuit_halt",
            f"Reason: {reason}\nMode: {'DRY-RUN' if self.dry_run else 'LIVE'}\nEquity: {account_equity}",
            title="Breakout Bot Circuit Breaker Halted",
        )

    def _check_circuit_breakers(self, account: Dict[str, Any]) -> bool:
        """Return True when a circuit-breaker should stop the session."""
        try:
            current_equity = float(account.get("equity", 0.0) or 0.0)
        except Exception:
            current_equity = 0.0

        if self.session_start_equity is None and current_equity > 0:
            self.session_start_equity = current_equity

        if self.max_daily_drawdown_pct is not None and self.session_start_equity and self.session_start_equity > 0:
            drawdown_pct = max(0.0, (self.session_start_equity - current_equity) / self.session_start_equity)
            if drawdown_pct >= float(self.max_daily_drawdown_pct):
                self._trigger_halt(
                    f"Daily drawdown limit exceeded ({drawdown_pct:.2%} >= {float(self.max_daily_drawdown_pct):.2%})",
                    account_equity=current_equity,
                )
                return True

        if self.max_consecutive_losses is not None and self.consecutive_losses >= int(self.max_consecutive_losses):
            self._trigger_halt(
                f"Consecutive loss limit reached ({self.consecutive_losses}/{int(self.max_consecutive_losses)})",
                account_equity=current_equity,
            )
            return True

        return False

    def _check_test_hook_halt(self, loop_count: int, account_equity: Optional[float] = None) -> bool:
        """Return True when deterministic halt test hook is configured and triggered."""
        if self.force_halt_after_loops is None:
            return False
        try:
            threshold = int(self.force_halt_after_loops)
        except (TypeError, ValueError):
            return False
        if loop_count >= threshold:
            reason = self.force_halt_reason or f"Forced halt test hook at loop {threshold}"
            self._trigger_halt(reason, account_equity=account_equity)
            return True
        return False

    def _stop_requested(self) -> bool:
        """Check whether a manual scan-stop request has been signaled by the UI."""
        return STOP_SCANS_FLAG_PATH.exists()
    
    def run(self):
        """Run the main trading loop."""
        _write_active_bot_process_state()
        self._write_runtime_status("starting", "Trading session starting")
        self.logger.logger.info("="*60)
        self.logger.logger.info("TRADING SESSION STARTED")
        if self.dry_run:
            self.logger.logger.warning("DRY-RUN MODE ENABLED: no live orders will be submitted")
        self.logger.logger.info("="*60)
        
        try:
            # Get account info
            account = alpaca_client.get_account()
            self.session_start_equity = float(account.get("equity", 0.0) or 0.0)
            self.logger.logger.info(f"Account equity: ${account['equity']:,.2f}")
            self.logger.logger.info(f"Buying power: ${account['buying_power']:,.2f}")
            self._perform_startup_reconciliation()
            if self.entry_lockout and self.entry_lockout_reason:
                self.logger.logger.warning(
                    "Entry lockout active from startup reconciliation. "
                    "New entries are blocked until reset and symbol state alignment."
                )
            
            # Main loop
            loop_count = 0
            loop_interval = self.config.get("loop_interval_seconds", 60)
            if self.max_loops is not None:
                self.logger.logger.info(f"Loop limit enabled: {self.max_loops} iteration(s)")

            def _can_run_loop() -> bool:
                return utils.is_market_open() or self.bypass_market_hours
            
            while _can_run_loop():
                if self._stop_requested():
                    self.logger.logger.warning("Manual stop requested. Ending trading session.")
                    self._write_runtime_status("stopped", "Manual stop flag requested")
                    break

                try:
                    account = alpaca_client.get_account()
                except Exception as e:
                    self.logger.log_error(f"Failed to refresh account snapshot: {e}", exc_info=e)
                    account = account

                if self._check_circuit_breakers(account):
                    break

                if self._check_test_hook_halt(
                    loop_count,
                    account_equity=float(account.get("equity", 0.0) or 0.0),
                ):
                    break

                self._write_runtime_status("running", "Trading loop active", account_equity=float(account.get("equity", 0.0) or 0.0))

                loop_count += 1
                self.logger.logger.debug(f"\n--- Loop {loop_count} ---")
                
                try:
                    self._loop_iteration(account)
                except Exception as e:
                    self.logger.log_error(f"Error in loop iteration: {e}", exc_info=e)

                if self.max_loops is not None and loop_count >= self.max_loops:
                    self.logger.logger.info(f"Reached max loops ({self.max_loops}). Ending session.")
                    self._write_runtime_status("stopped", f"Reached max loops ({self.max_loops})")
                    break
                
                # Check remaining market time
                remaining = utils.market_hours_remaining()
                if not self.bypass_market_hours and remaining.total_seconds() < loop_interval:
                    self.logger.logger.info(f"Market closing soon ({remaining}). Skipping sleep.")
                    self._write_runtime_status("stopped", "Market closing soon")
                    break
                
                # Sleep before next iteration
                self.logger.logger.debug(f"Sleeping for {loop_interval}s...")
                time.sleep(loop_interval)
        
        except KeyboardInterrupt:
            self.logger.logger.info("Trading interrupted by user")
            self._write_runtime_status("stopped", "Interrupted by user")
        except Exception as e:
            self.logger.log_error(f"Fatal error in trading loop: {e}", exc_info=e)
            self._write_runtime_status("error", f"Fatal error: {e}")
            notify_discord(
                "fatal_error",
                f"Fatal error in trading loop: {e}",
                title="Breakout Bot Fatal Error",
            )
        finally:
            self._close_session()
            _clear_active_bot_process_state()
    
    def _loop_iteration(self, account: Dict[str, Any]):
        """Execute one iteration of the trading loop.
        
        Args:
            account: Current account information
        """
        symbols = self.config.get("symbols", [])
        timeframe = self.config.get("timeframe", "5Min")
        lookback = self.config.get("lookback", 50)
        scanner_cfg = self.config.get("scanner", {})
        
        # Check active positions for exits
        self._check_exits(account)

        selected_symbols = self._select_scan_symbols(symbols, scanner_cfg)

        # Scan and rank symbols, then evaluate risk on top candidates.
        ranked_candidates = self._scan_and_rank(selected_symbols, timeframe, lookback, scanner_cfg)

        for candidate in ranked_candidates:
            if self._stop_requested():
                self.logger.logger.warning("Manual stop requested. Halting candidate evaluation.")
                break

            symbol = candidate["symbol"]
            signal = candidate["signal"]

            self.logger.log_signal(symbol, signal)

            # Evaluate risk
            risk_config = self.config.get("risk", {})
            risk_config["current_trades_today"] = self.trades_today
            risk_config["current_open_risk"] = self.open_risk_dollars
            risk_config["current_open_positions"] = len(self.active_trades)
            risk_config["symbol"] = symbol
            risk_config["symbol_cooldown_minutes"] = self.symbol_cooldown_minutes
            risk_config["symbol_cooldowns"] = self.symbol_cooldowns
            risk_config["current_time"] = datetime.now().timestamp()

            risk_decision = evaluate_risk(account, signal, risk_config)

            if self.entry_lockout:
                self.logger.log_skip(symbol, self.entry_lockout_reason or "Safe-mode entry lockout active")
                continue

            if not risk_decision.get("allowed"):
                reason = risk_decision.get("reason", "Unknown reason")
                self.logger.log_skip(symbol, reason)
                continue

            self._execute_buy(symbol, signal, risk_decision)

    def _select_scan_symbols(self, symbols: List[str], scanner_cfg: Dict[str, Any]) -> List[str]:
        """Select scan symbols based on max cap and selection strategy."""
        if not symbols:
            return []

        max_symbols = scanner_cfg.get("max_symbols")
        if max_symbols is None:
            return symbols

        try:
            max_symbols = int(max_symbols)
        except (TypeError, ValueError):
            return symbols

        if max_symbols <= 0 or max_symbols >= len(symbols):
            return symbols

        selection = str(scanner_cfg.get("scan_selection", "rotating")).lower()

        if selection == "random":
            return self._rng.sample(symbols, max_symbols)

        if selection == "rotating":
            start = self.scan_cursor % len(symbols)
            end = start + max_symbols
            if end <= len(symbols):
                selected = symbols[start:end]
            else:
                overflow = end - len(symbols)
                selected = symbols[start:] + symbols[:overflow]
            self.scan_cursor = (start + max_symbols) % len(symbols)
            return selected

        return symbols[:max_symbols]

    def _scan_and_rank(
        self,
        symbols: List[str],
        timeframe: str,
        lookback: int,
        scanner_cfg: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Scan symbols, score candidates, and return ranked BUY list for execution."""
        min_price = scanner_cfg.get("min_price")
        max_price = scanner_cfg.get("max_price")
        min_avg_volume = scanner_cfg.get("min_average_volume")
        top_candidates = int(scanner_cfg.get("top_candidates", 20) or 20)

        scored_buy: List[Dict[str, Any]] = []
        scored_all: List[Dict[str, Any]] = []
        scanned = 0
        buy_signals = 0

        for symbol in symbols:
            if self._stop_requested():
                self.logger.logger.warning("Manual stop requested during symbol scan.")
                break

            scanned += 1
            try:
                bars = alpaca_client.get_bars(symbol, timeframe, lookback)
            except Exception as e:
                self.logger.log_error(f"Error fetching bars for {symbol}: {e}", exc_info=e)
                continue

            if not bars:
                continue

            last_close = float(bars[-1]["close"])
            if min_price is not None and last_close < float(min_price):
                continue
            if max_price is not None and last_close > float(max_price):
                continue

            if min_avg_volume is not None:
                recent_volumes = [float(b["volume"]) for b in bars[-20:]]
                avg_volume = statistics.mean(recent_volumes) if recent_volumes else 0.0
                if avg_volume < float(min_avg_volume):
                    continue

            signal = evaluate_strategy(bars, symbol, self.config.get("strategy", {}))
            score = self._score_candidate(signal, bars, scanner_cfg)
            signal["score"] = round(score, 4)

            scored_row = {
                "symbol": symbol,
                "signal": signal,
                "score": score,
            }
            scored_all.append(scored_row)

            if signal.get("action") == "BUY":
                buy_signals += 1
                scored_buy.append(scored_row)

        scored_buy.sort(key=lambda c: c["score"], reverse=True)
        ranked_buy = scored_buy[:max(1, top_candidates)] if scored_buy else []

        scored_all.sort(key=lambda c: c["score"], reverse=True)
        ranked_analyzed = scored_all[:max(1, top_candidates)] if scored_all else []

        self.logger.logger.info(
            f"SCAN | scanned={scanned} buy_signals={buy_signals} selected={len(ranked_buy)}"
        )
        if ranked_analyzed:
            preview = ", ".join([f"{c['symbol']}:{c['score']:.2f}" for c in ranked_analyzed[:5]])
            self.logger.logger.info(f"RANKED | analyzed top candidates: {preview}")
        if ranked_buy:
            preview_buy = ", ".join([f"{c['symbol']}:{c['score']:.2f}" for c in ranked_buy[:5]])
            self.logger.logger.info(f"RANKED | buy candidates: {preview_buy}")

        self._write_scanner_snapshot(scanned, buy_signals, ranked_buy, ranked_analyzed)

        return ranked_buy

    def _write_scanner_snapshot(
        self,
        scanned: int,
        buy_signals: int,
        ranked_buy: List[Dict[str, Any]],
        ranked_analyzed: List[Dict[str, Any]],
    ) -> None:
        """Persist latest scanner/ranking result for UI visualization."""
        try:
            DATA_UI_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "scanned": scanned,
                "buy_signals": buy_signals,
                "selected": len(ranked_buy),
                "top": [
                    {
                        "symbol": c["symbol"],
                        "score": round(float(c.get("score", 0.0)), 4),
                        "action": c.get("signal", {}).get("action", "NONE"),
                        "confidence": c.get("signal", {}).get("confidence"),
                        "entry_level": c.get("signal", {}).get("entry_level"),
                        "stop_level": c.get("signal", {}).get("stop_level"),
                        "target_level": c.get("signal", {}).get("target_level"),
                        "volume_check": c.get("signal", {}).get("volume_check"),
                    }
                    for c in ranked_buy
                ],
                "top_analyzed": [
                    {
                        "symbol": c["symbol"],
                        "score": round(float(c.get("score", 0.0)), 4),
                        "action": c.get("signal", {}).get("action", "NONE"),
                        "confidence": c.get("signal", {}).get("confidence"),
                        "entry_level": c.get("signal", {}).get("entry_level"),
                        "stop_level": c.get("signal", {}).get("stop_level"),
                        "target_level": c.get("signal", {}).get("target_level"),
                        "volume_check": c.get("signal", {}).get("volume_check"),
                    }
                    for c in ranked_analyzed
                ],
            }
            SCANNER_SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            self.logger.log_error(f"Failed to write scanner snapshot: {e}")

    def _score_candidate(self, signal: Dict[str, Any], bars: List[Dict[str, Any]], scanner_cfg: Dict[str, Any]) -> float:
        """Score a BUY candidate for ranking.

        Components:
        - strategy confidence
        - breakout strength above recent highs
        - volume ratio on latest bar
        - short-term momentum
        """
        confidence = float(signal.get("confidence", 0.0))
        close = float(bars[-1]["close"])
        weights = scanner_cfg.get("score_weights", {})
        w_confidence = float(weights.get("confidence", 50.0))
        w_breakout = float(weights.get("breakout", 200.0))
        w_volume = float(weights.get("volume", 10.0))
        w_momentum = float(weights.get("momentum", 100.0))
        volume_ratio_cap = float(scanner_cfg.get("volume_ratio_cap", 5.0))

        prev_highs = [float(b["high"]) for b in bars[-21:-1]] if len(bars) > 1 else [close]
        resistance = max(prev_highs) if prev_highs else close
        breakout_strength = max(0.0, (close - resistance) / resistance) if resistance > 0 else 0.0

        prev_volumes = [float(b["volume"]) for b in bars[-21:-1]] if len(bars) > 1 else [1.0]
        avg_volume = statistics.mean(prev_volumes) if prev_volumes else 1.0
        curr_volume = float(bars[-1]["volume"])
        volume_ratio = (curr_volume / avg_volume) if avg_volume > 0 else 1.0

        momentum_period = min(10, len(bars) - 1)
        if momentum_period > 0:
            base_close = float(bars[-1 - momentum_period]["close"])
            momentum = ((close - base_close) / base_close) if base_close > 0 else 0.0
        else:
            momentum = 0.0

        score = (
            confidence * w_confidence
            + breakout_strength * w_breakout
            + min(volume_ratio, volume_ratio_cap) * w_volume
            + max(momentum, -0.2) * w_momentum
        )
        return score
    
    def _evaluate_symbol(self, symbol: str, timeframe: str, lookback: int,
                        account: Dict[str, Any]):
        """Evaluate a single symbol for breakout signals.
        
        Args:
            symbol: Stock symbol
            timeframe: Timeframe (e.g., '5Min')
            lookback: Number of bars to retrieve
            account: Current account information
        """
        # Fetch bars
        bars = alpaca_client.get_bars(symbol, timeframe, lookback)
        if not bars:
            self.logger.logger.warning(f"No bars for {symbol}")
            return
        
        # Evaluate strategy
        signal = evaluate_strategy(bars, symbol)
        self.logger.log_signal(symbol, signal)
        
        if signal["action"] != "BUY":
            self.logger.log_no_signal(symbol)
            return
        
        # Evaluate risk
        risk_config = self.config.get("risk", {})
        risk_config["current_trades_today"] = self.trades_today
        risk_config["current_open_risk"] = self.open_risk_dollars
        
        risk_decision = evaluate_risk(account, signal, risk_config)
        
        if not risk_decision.get("allowed"):
            reason = risk_decision.get("reason", "Unknown reason")
            self.logger.log_skip(symbol, reason)
            return
        
        # Execute trade
        self._execute_buy(symbol, signal, risk_decision)
    
    def _execute_buy(self, symbol: str, signal: Dict[str, Any],
                    risk_decision: Dict[str, Any]):
        """Execute a buy order.
        
        Args:
            symbol: Stock symbol
            signal: Strategy signal
            risk_decision: Risk manager decision
        """
        shares = risk_decision.get("shares")
        entry_price = signal.get("entry_level")
        stop_loss = signal.get("stop_level")
        target = signal.get("target_level")
        
        # Build order
        order_params = {
            "symbol": symbol,
            "qty": shares,
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
            "stop_loss": stop_loss,
            "take_profit": target,
        }
        
        try:
            # In dry-run mode, simulate a submitted order instead of calling the broker
            if self.dry_run:
                order = {
                    "id": f"dryrun-{symbol}-{int(datetime.now().timestamp())}",
                    "symbol": symbol,
                    "qty": int(shares or 0),
                    "side": "buy",
                    "status": "simulated",
                    "filled_qty": int(shares or 0),
                    "filled_avg_price": float(entry_price) if entry_price is not None else None,
                    "created_at": datetime.now().isoformat(),
                    "type": "market",
                }
                self.logger.logger.info(
                    f"DRY_RUN | Simulated BUY {symbol} qty={shares} entry={entry_price}"
                )
                self.logger.log_order(order)
            else:
                # Submit order
                order = submit_order(order_params, logger=self.logger)
            order_id = order.get("id")
            
            # Track trade
            risk_dollars = risk_decision.get("risk_dollars", 0)
            self.active_trades[symbol] = {
                "order_id": order_id,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "target": target,
                "shares": shares,
                "entry_time": datetime.now(),
                "risk_dollars": risk_dollars,
            }
            
            self.trades_today += 1
            self.open_risk_dollars += risk_dollars
            
            self.logger.log_trade_entry(symbol, entry_price, stop_loss, target,
                                       shares, order_id)
            
            self.logger.logger.info(f"Trades today: {self.trades_today} | "
                                   f"Open risk: ${self.open_risk_dollars:,.2f}")
        
        except Exception as e:
            self.logger.log_error(f"Failed to execute buy for {symbol}: {e}", exc_info=e)
    
    def _check_exits(self, account: Dict[str, Any]):
        """Check active positions for exit conditions.
        
        Args:
            account: Current account information
        """
        if self.dry_run:
            position_map = {}
            for symbol in self.active_trades.keys():
                bars = alpaca_client.get_bars(symbol, self.config.get("timeframe", "5Min"), lookback=1)
                if bars:
                    position_map[symbol] = {"symbol": symbol, "current_price": bars[-1]["close"]}
        else:
            positions = alpaca_client.get_open_positions()
            position_map = {p["symbol"]: p for p in positions}
        
        # Check each active trade
        symbols_to_remove = []
        for symbol, trade in self.active_trades.items():
            if symbol not in position_map:
                # Position was closed externally
                self.logger.logger.info(f"{symbol} position closed externally")
                symbols_to_remove.append(symbol)
                continue
            
            position = position_map[symbol]
            current_price = position["current_price"]
            entry_price = trade["entry_price"]
            stop_loss = trade["stop_loss"]
            target = trade["target"]
            
            # Check stop loss
            if current_price <= stop_loss:
                self._close_trade(symbol, current_price, "stop_loss")
                symbols_to_remove.append(symbol)
                continue
            
            # Check target
            if current_price >= target:
                self._close_trade(symbol, current_price, "take_profit")
                symbols_to_remove.append(symbol)
                continue
            
            # Check timeout (e.g., hold for max 1 hour per trade)
            max_hold_minutes = self.config.get("max_hold_minutes", 60)
            hold_duration = datetime.now() - trade["entry_time"]
            if hold_duration.total_seconds() > max_hold_minutes * 60:
                self.logger.logger.info(f"{symbol} timeout - held for {max_hold_minutes}m")
                self._close_trade(symbol, current_price, "timeout")
                symbols_to_remove.append(symbol)
        
        # Remove closed trades from tracking
        for symbol in symbols_to_remove:
            trade = self.active_trades.pop(symbol)
            self.open_risk_dollars -= trade.get("risk_dollars", 0)
    
    def _close_trade(self, symbol: str, exit_price: float, reason: str):
        """Close a trade.
        
        Args:
            symbol: Stock symbol
            exit_price: Price at exit
            reason: Reason for exit (stop_loss, take_profit, timeout, etc.)
        """
        if symbol not in self.active_trades:
            return
        
        trade = self.active_trades[symbol]
        entry_price = trade["entry_price"]
        shares = trade["shares"]
        
        # Calculate P&L
        pnl = (exit_price - entry_price) * shares
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
        
        try:
            # Close position unless we're simulating
            if self.dry_run:
                self.logger.logger.info(
                    f"DRY_RUN | Simulated CLOSE {symbol} qty={shares} exit={exit_price} reason={reason}"
                )
            else:
                close_position(symbol, qty=shares, logger=self.logger)
            
            # Log exit
            self.logger.log_exit(symbol, exit_price, pnl, pnl_pct,
                               order_id=trade["order_id"], reason=reason)
            
            # Update session stats
            self.session_pnl += pnl
            self.trades_closed += 1
            if pnl > 0:
                self.wins += 1
                self.consecutive_losses = 0
            elif pnl < 0:
                self.consecutive_losses += 1

            if self.symbol_cooldown_minutes > 0:
                self.symbol_cooldowns[symbol] = datetime.now().timestamp()
            
            self.logger.logger.info(f"Trade closed: {symbol} | "
                                   f"P&L: {pnl:+.2f} ({pnl_pct:+.2f}%) | "
                                   f"Session P&L: {self.session_pnl:+.2f}")
        
        except Exception as e:
            self.logger.log_error(f"Failed to close {symbol}: {e}", exc_info=e)
    
    def _close_session(self):
        """Close the trading session and log summary."""
        self.logger.logger.info("="*60)
        self.logger.logger.info("CLOSING TRADING SESSION")
        self.logger.logger.info("="*60)
        
        # Log summary
        session_end = datetime.now()
        duration = session_end - self.session_start
        win_rate = (self.wins / self.trades_closed * 100) if self.trades_closed > 0 else 0
        
        self.logger.log_summary(self.session_start, session_end, self.trades_closed,
                               self.session_pnl, win_rate)
        summary_text = (
            f"Duration: {session_end - self.session_start}\n"
            f"Trades: {self.trades_closed}\n"
            f"P/L: {self.session_pnl:+.2f}\n"
            f"Win Rate: {win_rate:.1f}%\n"
            f"Status: {'HALTED' if self.halt_reason else 'ENDED'}"
        )
        notify_discord("session_summary", summary_text, title="Breakout Bot Session Summary")
        if self.halt_reason:
            self._write_runtime_status("halted", self.halt_reason)
        else:
            self._write_runtime_status("stopped", "Session ended normally")
        
        # Log final positions
        if self.dry_run:
            # In dry-run mode, broker positions are not modified by the session.
            self.logger.log_positions([])
        else:
            try:
                positions = alpaca_client.get_open_positions()
                self.logger.log_positions(positions)
            except Exception as e:
                self.logger.log_error(f"Failed to fetch final positions: {e}")
        
        self.logger.logger.info("="*60)
        self.logger.logger.info("SESSION ENDED")
        self.logger.logger.info("="*60)


def _run_smoke_test() -> int:
    """Perform a one-shot Alpaca paper-account connectivity check."""
    print("\n" + "="*60)
    print("ALPACA PAPER ACCOUNT SMOKE TEST")
    print("="*60)
    print("This checks connectivity and data access without submitting orders.")

    try:
        account = alpaca_client.get_account()
        print("[OK] Connected to Alpaca account")
        print(f"  Equity: ${account['equity']:,.2f}")
        print(f"  Buying power: ${account['buying_power']:,.2f}")
        print(f"  Status: {account['status']}")

        bars = alpaca_client.get_bars("AAPL", "5Min", lookback=3)
        print(f"[OK] Retrieved {len(bars)} recent bars for AAPL")

        positions = alpaca_client.get_open_positions()
        print(f"[OK] Retrieved {len(positions)} open positions")

        return 0
    except Exception as e:
        print(f"[ERR] Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run the breakout trading bot")
    parser.add_argument("--skip-market-check", action="store_true",
                        help="Bypass market-hours checks for smoke testing")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Test Alpaca paper account connectivity and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run strategy/risk loop without submitting live orders")
    parser.add_argument("--max-loops", type=int, default=None,
                        help="Limit strategy loop iterations (recommended with --dry-run)")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbols override (e.g., AAPL,MSFT,SPY)")
    parser.add_argument("--append-symbols", action="store_true",
                        help="Append --symbols to configured/universe symbols instead of replacing")
    parser.add_argument("--symbol-universe", choices=["config", "us-all"], default="config",
                        help="Symbol source: config list or all active tradeable US equities")
    parser.add_argument("--max-symbols", type=int, default=200,
                        help="Max symbols scanned per loop (set <=0 for no cap)")
    parser.add_argument("--scan-selection", choices=["first", "random", "rotating"], default="rotating",
                        help="How to choose symbols when --max-symbols caps the universe")
    parser.add_argument("--top-candidates", type=int, default=None,
                        help="Number of top ranked symbols to evaluate for entries each loop")
    parser.add_argument("--min-price", type=float, default=None,
                        help="Minimum last price filter for scanner")
    parser.add_argument("--max-price", type=float, default=None,
                        help="Maximum last price filter for scanner")
    parser.add_argument("--min-average-volume", type=float, default=None,
                        help="Minimum average volume filter (20-bar avg)")
    parser.add_argument("--volume-ratio-cap", type=float, default=None,
                        help="Cap applied to volume ratio term in scoring")
    parser.add_argument("--weight-confidence", type=float, default=None,
                        help="Score weight for signal confidence component")
    parser.add_argument("--weight-breakout", type=float, default=None,
                        help="Score weight for breakout-strength component")
    parser.add_argument("--weight-volume", type=float, default=None,
                        help="Score weight for volume-ratio component")
    parser.add_argument("--weight-momentum", type=float, default=None,
                        help="Score weight for momentum component")
    parser.add_argument("--risk-max-trades-per-day", type=int, default=None,
                        help="Risk guardrail override: max trades allowed per day")
    parser.add_argument("--risk-max-risk-pct", type=float, default=None,
                        help="Risk guardrail override: max equity risk per trade")
    parser.add_argument("--risk-max-open-risk-pct", type=float, default=None,
                        help="Risk guardrail override: max total open risk as equity fraction")
    parser.add_argument("--risk-max-position-pct", type=float, default=None,
                        help="Risk guardrail override: max position notional as equity fraction")
    parser.add_argument("--risk-max-open-positions", type=int, default=None,
                        help="Risk guardrail override: max concurrent open positions")
    parser.add_argument("--risk-symbol-cooldown-minutes", type=float, default=None,
                        help="Risk guardrail override: symbol cooldown minutes after an exit")
    parser.add_argument("--risk-max-daily-drawdown-pct", type=float, default=None,
                        help="Risk guardrail override: max drawdown from session-start equity")
    parser.add_argument("--risk-max-consecutive-losses", type=int, default=None,
                        help="Risk guardrail override: max consecutive losing exits before halt")
    parser.add_argument("--test-force-halt-after-loops", type=int, default=None,
                        help="Test hook: force a circuit-breaker halt after N loops (0 = immediate)")
    parser.add_argument("--test-force-halt-reason", type=str, default="Forced halt test hook",
                        help="Test hook: halt reason text written when forced halt triggers")
    parser.add_argument("--reset-runtime-status", action="store_true",
                        help="Reset persisted runtime breaker state and exit")
    parser.add_argument("--reset-runtime-clear-cooldowns", action="store_true",
                        help="Used with --reset-runtime-status to also clear symbol cooldown history")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("BREAKOUT TRADING BOT")
    print("="*60)
    
    try:
        # Load configuration
        print("Loading configuration...")
        config = utils.load_config()

        resolved_symbols = _resolve_symbols(
            config,
            symbol_universe=args.symbol_universe,
            symbols_csv=args.symbols,
            append_symbols=args.append_symbols,
        )
        config["symbols"] = resolved_symbols
        scanner_cfg = _resolve_scanner_config(config, args)
        risk_cfg = _resolve_risk_config(config, args)

        if args.test_force_halt_after_loops is not None:
            if args.test_force_halt_after_loops < 0:
                print("\n[ERR] --test-force-halt-after-loops must be >= 0")
                return 1
            hooks = config.setdefault("test_hooks", {})
            hooks["force_halt_after_loops"] = int(args.test_force_halt_after_loops)
            hooks["force_halt_reason"] = str(args.test_force_halt_reason)

        print(f"[OK] Config loaded")
        print(f"  Symbols ({len(config.get('symbols', []))}): {config.get('symbols')[:10]}")
        if len(config.get("symbols", [])) > 10:
            print("  ... (truncated preview)")
        print(f"  Scanner top candidates: {scanner_cfg.get('top_candidates')}")
        if scanner_cfg.get("min_price") is not None or scanner_cfg.get("max_price") is not None:
            print(f"  Price filter: {scanner_cfg.get('min_price')} - {scanner_cfg.get('max_price')}")
        if scanner_cfg.get("min_average_volume") is not None:
            print(f"  Min avg volume: {scanner_cfg.get('min_average_volume')}")
        print(f"  Volume ratio cap: {scanner_cfg.get('volume_ratio_cap')}")
        print(f"  Score weights: {scanner_cfg.get('score_weights')}")
        print(f"  Scan max symbols: {scanner_cfg.get('max_symbols') or 'unlimited'}")
        print(f"  Scan selection: {scanner_cfg.get('scan_selection')}")
        print(f"  Timeframe: {config.get('timeframe')}")
        print(f"  Max trades/day: {risk_cfg.get('max_trades_per_day')}")
        print(f"  Max risk/trade: {risk_cfg.get('max_risk_pct')}")
        print(f"  Max open risk: {risk_cfg.get('max_open_risk_pct')}")
        print(f"  Max position size: {risk_cfg.get('max_position_pct')}")
        print(f"  Max open positions: {risk_cfg.get('max_open_positions')}")
        print(f"  Symbol cooldown (min): {risk_cfg.get('symbol_cooldown_minutes')}")
        print(f"  Max daily drawdown: {risk_cfg.get('max_daily_drawdown_pct')}")
        print(f"  Max consecutive losses: {risk_cfg.get('max_consecutive_losses')}")
        if args.test_force_halt_after_loops is not None:
            print(f"  Test forced halt loops: {args.test_force_halt_after_loops}")

        if args.reset_runtime_status:
            session = TradingSession(
                config,
                dry_run=True,
                max_loops=1,
                bypass_market_hours=True,
            )
            session._reset_runtime_context(clear_cooldowns=args.reset_runtime_clear_cooldowns)
            print("[OK] Runtime breaker state reset.")
            return 0

        if args.smoke_test:
            return _run_smoke_test()
        
        # Check if market is open
        print(f"\nChecking market status...")
        now = utils.now_market()
        print(f"  Current time: {now}")
        market_open = utils.is_market_open()
        print(f"  Market open: {market_open}")
        
        if not args.skip_market_check and not market_open:
            next_open = utils.next_market_open()
            print(f"\n[ERR] Market is closed. Next open: {next_open}")
            return 1
        if args.skip_market_check and not market_open:
            print("\n[WARN] Market check bypassed. Running session anyway.")
        
        # Start trading session
        if args.dry_run:
            print("\n[OK] Dry-run mode enabled. Orders will be simulated only.")
        if args.max_loops is not None:
            if args.max_loops < 1:
                print("\n[ERR] --max-loops must be >= 1")
                return 1
            print(f"[OK] Loop limit: {args.max_loops}")
        print("\n[OK] Starting trading session...")
        session = TradingSession(
            config,
            dry_run=args.dry_run,
            max_loops=args.max_loops,
            bypass_market_hours=args.skip_market_check,
        )
        session.run()
        
        return 0
    
    except FileNotFoundError as e:
        print(f"[ERR] Configuration error: {e}")
        return 1
    except Exception as e:
        print(f"[ERR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
