# Breakout Trading Bot

Python trading bot for breakout strategy experiments with Alpaca paper trading.

Use this repository in paper mode only.

## Prerequisites

- Python 3.11+ (project currently tested with local Python 3.14 install)
- Alpaca paper account API key and secret

## Setup

```bash
# from repository root
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe -m pip install -r requirements.txt
```

Create `.env` in the repo root and set:

```env
ALPACA_KEY_ID=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_PAPER=True
DISCORD_WEBHOOK_URL=
DISCORD_NOTIFY_EVENTS=
```

`ALPACA_PAPER=True` means paper account mode by default.
Set `ALPACA_PAPER=False` only when you intentionally want live trading mode.

Discord notifications are optional:
- `DISCORD_WEBHOOK_URL`: Discord incoming webhook URL
- `DISCORD_NOTIFY_EVENTS`: comma-separated event keys to send (optional)
  - Python defaults: `circuit_halt,fatal_error,preflight_block,reconciliation_mismatch,schedule_block,session_summary,watchdog_restart,watchdog_stop`
  - Watchdog defaults when unset: `watchdog_restart,watchdog_stop,watchdog_escalation`

Update `config/settings.yaml` for symbols/timeframe/risk values.

## CLI Usage

### 1) Safe connectivity check

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --smoke-test
```

What it does:
- checks Alpaca account connectivity
- fetches sample bars
- fetches open positions
- does not place orders

### 2) Dry-run (no live orders)

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run
```

Optional deterministic testing outside market hours:

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --skip-market-check --max-loops 1
```

Important flags:
- `--dry-run`: simulates order submits/closes
- `--skip-market-check`: allows run when market is closed
- `--max-loops N`: run exactly N iterations, then exit

### 2b) Run additional symbols without editing config

Replace symbols for a run:

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --symbols AAPL,MSFT,NVDA
```

Append symbols to configured list:

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --symbols AMD,TSLA --append-symbols
```

Use all active tradeable US equities with a cap:

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --symbol-universe us-all --max-symbols 300
```

Rank only best strategy candidates (example with filters):

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --symbol-universe us-all --max-symbols 500 --top-candidates 25 --min-price 5 --max-price 200 --min-average-volume 500000
```

Notes:
- `--symbol-universe us-all` can be very large; start with a conservative `--max-symbols`.
- Scanning all US stocks in one loop may require more compute/time and data permissions.
- `--top-candidates` limits trade evaluation to highest-ranked breakout setups per loop.

Scanner score weights are configurable in `config/settings.yaml` under `scanner.score_weights`:
- `confidence`
- `breakout`
- `volume`
- `momentum`

### 3) Normal run

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py
```

## PowerShell Helper Scripts

### Start the UI quickly

```powershell
./scripts/run_ui.ps1
```

Optional:

```powershell
./scripts/run_ui.ps1 -Port 8502
./scripts/run_ui.ps1 -Headless
./scripts/run_ui.ps1 -Address 127.0.0.1   # local-only binding
./scripts/run_ui.ps1 -Address tailscale    # prefer the host Tailscale IPv4
```

### Run bot with explicit account mode

Paper mode dry-run (recommended):

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SkipMarketCheck -MaxLoops 1
```

Paper mode with additional symbols:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -Symbols AAPL,MSFT,GOOGL
```

Paper mode with US universe (capped):

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SymbolUniverse us-all -MaxSymbols 300
```

By default, capped US-universe scans use rotating selection so each loop scans a different batch.
Use `-ScanSelection random` for random batches, or `-ScanSelection first` to keep the legacy fixed-first behavior.
Set `-MaxSymbols 0` for no scan cap.

Paper mode with ranking + filters:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SymbolUniverse us-all -MaxSymbols 500 -TopCandidates 25 -MinPrice 5 -MaxPrice 200 -MinAverageVolume 500000
```

Paper mode with custom score weights:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SymbolUniverse us-all -MaxSymbols 500 -TopCandidates 25 -WeightConfidence 60 -WeightBreakout 220 -WeightVolume 12 -WeightMomentum 90 -VolumeRatioCap 4
```

Smoke test in paper mode:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -SmokeTest
```

Live mode example (use extreme caution):

```powershell
./scripts/run_bot.ps1 -AccountMode live -LiveConfirmToken LIVE-TRADE-YES
```

Watchdog mode for unattended auto-restart:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SymbolUniverse us-all -MaxSymbols 500 -TopCandidates 25 -SkipMarketCheck -Watchdog
```

Paper mode with explicit circuit-breaker guardrails:

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SkipMarketCheck -Watchdog -RiskMaxOpenPositions 5 -RiskSymbolCooldownMinutes 30 -RiskMaxDailyDrawdownPct 0.03 -RiskMaxConsecutiveLosses 3
```

Watchdog halt-policy smoke test (forces immediate halt):

```powershell
./scripts/run_bot.ps1 -AccountMode paper -DryRun -SkipMarketCheck -Watchdog -TestForceHaltAfterLoops 0 -TestForceHaltReason "watchdog halt test"
```

Watchdog behavior:
- Restarts bot process on non-zero exit codes.
- If `data/ui/runtime_status.json` reports `status: halted`, watchdog stops restarts (`halted_runtime_breaker`).
- Uses exponential backoff between restarts.
- Stops after `-WatchdogMaxRestarts` attempts.
- Escalates to a hard stop when failures burst above threshold:
  - `-WatchdogEscalationFailures` failures within `-WatchdogEscalationWindowMinutes` minutes
  - writes watchdog status `halted_failure_burst`
  - sends a high-priority Discord alert (`watchdog_escalation`)
- Writes state/log artifacts to:
  - `data/ui/watchdog_state.json`
  - `data/logs/watchdog_runner.log`
- Create `data/ui/watchdog_stop.flag` to request watchdog shutdown.
- If runtime status reports `entry_lockout=true`, watchdog start is blocked (`blocked_preflight_lockout`) unless `-AllowLockoutStart` is set.

Runtime status and circuit-breaker state is written to:
- `data/ui/runtime_status.json`

Risk override flags (supported by both `src/main.py` and `scripts/run_bot.ps1`):
- `--risk-max-trades-per-day` / `-RiskMaxTradesPerDay`
- `--risk-max-risk-pct` / `-RiskMaxRiskPct`
- `--risk-max-open-risk-pct` / `-RiskMaxOpenRiskPct`
- `--risk-max-position-pct` / `-RiskMaxPositionPct`
- `--risk-max-open-positions` / `-RiskMaxOpenPositions`
- `--risk-symbol-cooldown-minutes` / `-RiskSymbolCooldownMinutes`
- `--risk-max-daily-drawdown-pct` / `-RiskMaxDailyDrawdownPct`
- `--risk-max-consecutive-losses` / `-RiskMaxConsecutiveLosses`

Test hook flags (supported by both `src/main.py` and `scripts/run_bot.ps1`):
- `--test-force-halt-after-loops` / `-TestForceHaltAfterLoops`
- `--test-force-halt-reason` / `-TestForceHaltReason`

Deterministic test hook flags (CLI only, useful for automated circuit-breaker tests):
- `--test-force-halt-after-loops N` forces a halted runtime state after loop `N` (`0` = immediate).
- `--test-force-halt-reason "text"` sets the halt reason written to `data/ui/runtime_status.json`.

Runtime breaker context persistence:
- `consecutive_losses` and `symbol_cooldowns` are persisted in `data/ui/runtime_status.json` and restored on restart.
- This keeps breaker protections active across watchdog/bot restarts.

Strict trading schedule gate:
- Configured under `automation.trading_window` in `config/settings.yaml`.
- Default window is Mon-Fri 09:30-16:00 America/New_York and is enabled by default.
- Bot will stop/avoid starting trading loops outside this window even when market checks are bypassed.

Startup preflight gate:
- Configured under `automation.preflight.enabled` in `config/settings.yaml` (default `true`).
- Market-data freshness controls are under `automation.preflight`:
  - `max_market_data_age_minutes` (default `20`)
  - `symbols_to_check` (default `3`)
- Blocks startup if any check fails, writing `status=blocked_preflight` to runtime status:
  - account status is not active
  - buying power is non-positive/unavailable
  - prior entry lockout is still active
  - prior halt reason is still present
  - stale or invalid latest market-data timestamps while market is open
- Sends `preflight_block` Discord event when a preflight check blocks startup.

Startup reconciliation safe mode:
- On session start, broker open positions are reconciled against locally tracked active positions.
- If they do not match, bot enters safe-mode entry lockout (no new entries) and writes lockout state to `data/ui/runtime_status.json`.
- Lockout can be acknowledged/reset from Home UI (`Acknowledge/Reset Halt`) after manual review.
- Optional dry-run bypass: set `automation.reconciliation.allow_dry_run_mismatch: true` to allow startup in dry-run mode when broker/local symbols mismatch.
  - Live mode still enforces lockout on mismatch.

Runtime reset controls:
- UI Home page provides:
  - `Acknowledge/Reset Halt`
  - `Reset Halt + Clear Cooldowns`
- CLI equivalents:
  - `--reset-runtime-status`
  - `--reset-runtime-clear-cooldowns` (used with `--reset-runtime-status`)

Schedule gate CLI overrides:
- `--schedule-enabled`
- `--schedule-disabled`
- `--schedule-start HH:MM`
- `--schedule-end HH:MM`
- `--schedule-weekdays 0,1,2,3,4`

Notification event keys:
- `circuit_halt`: circuit breaker halts a session
- `fatal_error`: unhandled runtime failure in trading loop
- `preflight_block`: startup preflight checklist blocked run startup
- `reconciliation_mismatch`: startup position reconciliation mismatch triggers safe-mode entry lockout
- `schedule_block`: strict schedule gate blocked startup or runtime loop continuation
- `session_summary`: session summary posted at session close
- `watchdog_restart`: watchdog restarting bot after non-zero exit
- `watchdog_stop`: watchdog stops (clean exit, stop flag, breaker-halt, or max restarts)
- `watchdog_escalation`: watchdog halted due to failure burst escalation policy

The script sets `ALPACA_PAPER` automatically per run:
- `-AccountMode paper` => `ALPACA_PAPER=True`
- `-AccountMode live` => `ALPACA_PAPER=False`
- Non-dry-run live mode requires: `-LiveConfirmToken LIVE-TRADE-YES`

### Check/kill rogue repo processes

List repo-scoped Python processes:

```powershell
./scripts/repo_processes.ps1 -List
```

Kill repo-scoped Python processes:

```powershell
./scripts/repo_processes.ps1 -Kill
```

Optional: target another process name:

```powershell
./scripts/repo_processes.ps1 -List -ProcessName "streamlit.exe"
```

## Streamlit UI

Run dashboard:

```bash
./scripts/run_ui.ps1 -Port 8501
```

Open:
- `http://localhost:8501`

### Performance page

The `Performance` page includes:
- Cumulative P/L chart over time
- Drawdown chart and max drawdown metrics
- Aggregated P/L chart with day/week/month toggle
- Monthly P/L bars
- Symbol-level P/L bars and sortable symbol summary table
- Downloadable CSV export for filtered results

Filters support date range, months, symbols, and side.

### Email report delivery from Performance page

Set these environment variables to enable `Send report email`:
- `REPORT_EMAIL_SMTP_HOST`
- `REPORT_EMAIL_SMTP_PORT` (example: `587`)
- `REPORT_EMAIL_SMTP_USERNAME`
- `REPORT_EMAIL_SMTP_PASSWORD`
- `REPORT_EMAIL_FROM` (optional, defaults to username)
- `REPORT_EMAIL_TO` (optional default recipient shown in UI)

The UI sends the currently filtered report as a CSV attachment.

### Access from Other Devices

#### Internal network (same LAN)

- Allow inbound TCP `8501` on the machine firewall running Streamlit.
- Find the host LAN IP (for example with `ipconfig`/`ifconfig`).
- Open from another device: `http://<HOST_LAN_IP>:8501`

#### External access (recommended: private network)

- Prefer a private tunnel/VPN such as Tailscale, ZeroTier, or WireGuard.
- Access the UI over the VPN address: `http://<vpn-host-ip>:8501`

##### Tailscale on Windows 11 (step-by-step)

1. Install Tailscale on the Windows 11 host running the UI.
   - Download from `https://tailscale.com/download`
   - Sign in to your Tailscale account (tailnet).
2. Install Tailscale on the remote device (laptop/phone) and sign in to the same tailnet.
3. On the host, copy the Tailscale IPv4 address from the Tailscale app (usually `100.x.x.x`).
4. Start the UI from repo root:

```powershell
cd C:\path\to\AutoTrading-Bot
./scripts/run_ui.ps1 -Port 8501
```

If PowerShell blocks `run_ui.ps1`, use the direct `python -m streamlit ...` command above, or run this once in the current PowerShell window before calling the script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
```

5. Allow inbound TCP `8501` on Windows Firewall (host):

```powershell
New-NetFirewallRule -DisplayName "AutoTradingBot Streamlit 8501 (Tailscale)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 -Profile Private,Domain
```

6. From the remote device (connected to Tailscale), open:
   - `http://<HOST_TAILSCALE_IP>:8501`
   - Example: `http://100.101.102.103:8501`
7. Lock down access in Tailscale admin:
   - Enable MFA/SSO policy for your users.
   - Restrict who can reach the host with ACLs.

Minimal ACL example (replace values for your tailnet):

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:trading-admins"],
      "dst": ["autotrading-host:8501"]
    }
  ],
  "tagOwners": {
    "tag:autotrading-host": ["group:trading-admins"]
  }
}
```

  Watchdog lockout override (use cautiously, after manual reconciliation review):

  ```powershell
  ./scripts/run_bot.ps1 -AccountMode paper -DryRun -SkipMarketCheck -Watchdog -AllowLockoutStart
  ```

Quick troubleshooting:
- Verify Streamlit is running on host and bound to port `8501`.
- Confirm both devices are connected to the same tailnet.
- Re-check Windows Firewall rule and host Tailscale IP.
- Restart Tailscale on host if connectivity is stale.

#### Public internet exposure (higher risk)

- Do not expose raw Streamlit directly on `8501`.
- Put a reverse proxy (Nginx/Caddy) in front with HTTPS and authentication.
- Forward router port `443` to the reverse proxy host.
- Use dynamic DNS or a static IP for stable access.

### UI Features

- One-shot command execution (`Run One-Shot`, `Run Smoke Test`)
- Account mode selector (`paper` or `live`) applied per UI run
- Live non-dry-run guard requiring token input `LIVE-TRADE-YES`
- Symbol controls for override/append and `us-all` universe mode
- Scanner controls for top-candidate ranking and price/volume filters
- Scanner score-weight controls (confidence/breakout/volume/momentum + volume cap)
- Persistent background runner (`Start Background`, `Stop Background`)
- Auto-refresh controls for live panels
- Account snapshot cards (equity, buying power, status)
- Run output panel (`stdout`/`stderr`)
- Bot log tail panel (`data/logs/bot_*.log`)
- Background runner log panel (`data/logs/background_runner.log`)
- Recent trades table (`data/trades/trades_*.csv`)
- Scanner snapshot table (`data/ui/scanner_snapshot.json`)

### Background Runner Persistence

- Runner state file: `data/ui/background_runner.json`
- Background log file: `data/logs/background_runner.log`
- The UI can reconnect to a running process after page refreshes or Streamlit restarts.

## Safety Notes for Live Trading

- Keep `Dry run mode` enabled until you have validated behavior thoroughly.
- Verify account mode before every run (`paper` vs `live`).
- Use `--max-loops` or `-MaxLoops` for controlled rollouts.
- For non-dry-run live mode, the guard token is required: `LIVE-TRADE-YES`.

## Common Verification Commands

```bash
# smoke test
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --smoke-test

# one-loop dry-run
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe src/main.py --dry-run --skip-market-check --max-loops 1

# focused tests
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe -m pytest -q tests/test_executor.py
```

## Project Layout

- `src/`: bot logic, Alpaca client, strategy, risk, logging, executor
- `config/settings.yaml`: runtime configuration
- `ui/Home.py`: Streamlit dashboard home page
- `data/logs/`: bot/background logs
- `data/trades/`: CSV trade journal output
