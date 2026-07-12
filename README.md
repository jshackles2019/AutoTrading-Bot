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
```

`ALPACA_PAPER=True` means paper account mode by default.
Set `ALPACA_PAPER=False` only when you intentionally want live trading mode.

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

The script sets `ALPACA_PAPER` automatically per run:
- `-AccountMode paper` => `ALPACA_PAPER=True`
- `-AccountMode live` => `ALPACA_PAPER=False`
- Non-dry-run live mode requires: `-LiveConfirmToken LIVE-TRADE-YES`

## Streamlit UI

Run dashboard:

```bash
C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe -m streamlit run ui/app.py
```

Open:
- `http://localhost:8501`

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
- `ui/app.py`: Streamlit dashboard
- `data/logs/`: bot/background logs
- `data/trades/`: CSV trade journal output
