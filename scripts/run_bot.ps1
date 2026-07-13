Param(
    [ValidateSet("paper", "live")]
    [string]$AccountMode = "paper",
    [switch]$DryRun,
    [switch]$SkipMarketCheck,
    [int]$MaxLoops,
    [switch]$SmokeTest,
    [string]$LiveConfirmToken,
    [string[]]$Symbols,
    [switch]$AppendSymbols,
    [ValidateSet("config", "us-all")]
    [string]$SymbolUniverse = "config",
    [int]$MaxSymbols = 200,
    [ValidateSet("first", "random", "rotating")]
    [string]$ScanSelection = "rotating",
    [int]$TopCandidates,
    [double]$MinPrice,
    [double]$MaxPrice,
    [double]$MinAverageVolume,
    [double]$WeightConfidence,
    [double]$WeightBreakout,
    [double]$WeightVolume,
    [double]$WeightMomentum,
    [double]$VolumeRatioCap,
    [int]$RiskMaxTradesPerDay,
    [double]$RiskMaxRiskPct,
    [double]$RiskMaxOpenRiskPct,
    [double]$RiskMaxPositionPct,
    [int]$RiskMaxOpenPositions,
    [double]$RiskSymbolCooldownMinutes,
    [double]$RiskMaxDailyDrawdownPct,
    [int]$RiskMaxConsecutiveLosses,
    [int]$TestForceHaltAfterLoops,
    [string]$TestForceHaltReason,
    [switch]$Watchdog,
    [switch]$AllowLockoutStart,
    [int]$WatchdogMaxRestarts = 10,
    [int]$WatchdogBaseBackoffSeconds = 5,
    [int]$WatchdogMaxBackoffSeconds = 120
)

$requiredLiveToken = "LIVE-TRADE-YES"
$BoundParams = $PSBoundParameters

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$dataUiDir = Join-Path $repoRoot "data\ui"
$dataLogsDir = Join-Path $repoRoot "data\logs"
$watchdogStatePath = Join-Path $dataUiDir "watchdog_state.json"
$watchdogLogPath = Join-Path $dataLogsDir "watchdog_runner.log"
$watchdogStopFlagPath = Join-Path $dataUiDir "watchdog_stop.flag"
$runtimeStatusPath = Join-Path $dataUiDir "runtime_status.json"

$discordWebhookUrl = [string]$env:DISCORD_WEBHOOK_URL
$discordNotifyEventsRaw = [string]$env:DISCORD_NOTIFY_EVENTS
if ([string]::IsNullOrWhiteSpace($discordNotifyEventsRaw)) {
    $discordNotifyEvents = @("watchdog_restart", "watchdog_stop")
} else {
    $discordNotifyEvents = @(
        $discordNotifyEventsRaw.Split(",") |
        ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

New-Item -ItemType Directory -Force -Path $dataUiDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataLogsDir | Out-Null

$python = "C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$env:ALPACA_PAPER = if ($AccountMode -eq "paper") { "True" } else { "False" }

if ($AccountMode -eq "live" -and -not $DryRun -and -not $SmokeTest) {
    if ($LiveConfirmToken -ne $requiredLiveToken) {
        throw "Live trading guard: pass -LiveConfirmToken $requiredLiveToken for non-dry-run live execution."
    }
}

function Write-WatchdogLog {
    Param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date).ToString("s"), $Message
    Add-Content -Path $watchdogLogPath -Value $line -Encoding utf8
}

function Send-DiscordNotification {
    Param(
        [string]$EventName,
        [string]$Message,
        [string]$Title = "Breakout Bot"
    )
    if ([string]::IsNullOrWhiteSpace($discordWebhookUrl)) {
        return
    }
    $eventKey = $EventName.Trim().ToLowerInvariant()
    if ($discordNotifyEvents -notcontains $eventKey) {
        return
    }
    $content = "**$Title**`n$Message`n$([DateTime]::Now.ToString('s'))"
    $payload = @{ content = $content }
    try {
        Invoke-RestMethod -Method Post -Uri $discordWebhookUrl -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 3) | Out-Null
    } catch {
        Write-WatchdogLog "Discord notify failed for ${eventKey}: $($_.Exception.Message)"
    }
}

function Write-WatchdogState {
    Param(
        [string]$Status,
        [int]$RestartCount,
        [int]$LastExitCode,
        [string]$Command,
        [string]$Message,
        [Nullable[DateTime]]$NextRestartAt
    )

    $payload = @{
        status = $Status
        updated_at = (Get-Date).ToString("o")
        restart_count = $RestartCount
        last_exit_code = $LastExitCode
        command = $Command
        account_mode = $AccountMode
        dry_run = [bool]$DryRun
        message = $Message
    }
    if ($null -ne $NextRestartAt -and $NextRestartAt.HasValue) {
        $payload.next_restart_at = $NextRestartAt.Value.ToString("o")
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $watchdogStatePath -Encoding utf8
}

function ConvertTo-QuotedArg {
    Param([string]$Value)
    if ($null -eq $Value) {
        return '""'
    }
    $escaped = $Value -replace '"', '\\"'
    return '"' + $escaped + '"'
}

function New-BotCommandParts {
    $parts = @("src/main.py")
    if ($SmokeTest) {
        $parts += "--smoke-test"
        return $parts
    }

    if ($DryRun) { $parts += "--dry-run" }
    if ($SkipMarketCheck) { $parts += "--skip-market-check" }

    if ($BoundParams.ContainsKey("MaxLoops")) {
        if ($MaxLoops -lt 1) {
            throw "MaxLoops must be >= 1"
        }
        $parts += @("--max-loops", "$MaxLoops")
    }

    if ($SymbolUniverse -ne "config") {
        $parts += @("--symbol-universe", $SymbolUniverse)
        if ($BoundParams.ContainsKey("MaxSymbols")) {
            $parts += @("--max-symbols", "$MaxSymbols")
        }
        if ($BoundParams.ContainsKey("ScanSelection")) {
            $parts += @("--scan-selection", $ScanSelection)
        }
    }

    if ($Symbols) {
        $symbolsCsv = ($Symbols -join ",")
        $parts += @("--symbols", $symbolsCsv)
        if ($AppendSymbols) {
            $parts += "--append-symbols"
        }
    }

    if ($BoundParams.ContainsKey("TopCandidates")) {
        $parts += @("--top-candidates", "$TopCandidates")
    }
    if ($BoundParams.ContainsKey("MinPrice")) {
        $parts += @("--min-price", "$MinPrice")
    }
    if ($BoundParams.ContainsKey("MaxPrice")) {
        $parts += @("--max-price", "$MaxPrice")
    }
    if ($BoundParams.ContainsKey("MinAverageVolume")) {
        $parts += @("--min-average-volume", "$MinAverageVolume")
    }
    if ($BoundParams.ContainsKey("WeightConfidence")) {
        $parts += @("--weight-confidence", "$WeightConfidence")
    }
    if ($BoundParams.ContainsKey("WeightBreakout")) {
        $parts += @("--weight-breakout", "$WeightBreakout")
    }
    if ($BoundParams.ContainsKey("WeightVolume")) {
        $parts += @("--weight-volume", "$WeightVolume")
    }
    if ($BoundParams.ContainsKey("WeightMomentum")) {
        $parts += @("--weight-momentum", "$WeightMomentum")
    }
    if ($BoundParams.ContainsKey("VolumeRatioCap")) {
        $parts += @("--volume-ratio-cap", "$VolumeRatioCap")
    }

    if ($BoundParams.ContainsKey("RiskMaxTradesPerDay")) {
        $parts += @("--risk-max-trades-per-day", "$RiskMaxTradesPerDay")
    }
    if ($BoundParams.ContainsKey("RiskMaxRiskPct")) {
        $parts += @("--risk-max-risk-pct", "$RiskMaxRiskPct")
    }
    if ($BoundParams.ContainsKey("RiskMaxOpenRiskPct")) {
        $parts += @("--risk-max-open-risk-pct", "$RiskMaxOpenRiskPct")
    }
    if ($BoundParams.ContainsKey("RiskMaxPositionPct")) {
        $parts += @("--risk-max-position-pct", "$RiskMaxPositionPct")
    }
    if ($BoundParams.ContainsKey("RiskMaxOpenPositions")) {
        $parts += @("--risk-max-open-positions", "$RiskMaxOpenPositions")
    }
    if ($BoundParams.ContainsKey("RiskSymbolCooldownMinutes")) {
        $parts += @("--risk-symbol-cooldown-minutes", "$RiskSymbolCooldownMinutes")
    }
    if ($BoundParams.ContainsKey("RiskMaxDailyDrawdownPct")) {
        $parts += @("--risk-max-daily-drawdown-pct", "$RiskMaxDailyDrawdownPct")
    }
    if ($BoundParams.ContainsKey("RiskMaxConsecutiveLosses")) {
        $parts += @("--risk-max-consecutive-losses", "$RiskMaxConsecutiveLosses")
    }
    if ($BoundParams.ContainsKey("TestForceHaltAfterLoops")) {
        $parts += @("--test-force-halt-after-loops", "$TestForceHaltAfterLoops")
    }
    if ($BoundParams.ContainsKey("TestForceHaltReason")) {
        $parts += @("--test-force-halt-reason", (ConvertTo-QuotedArg -Value $TestForceHaltReason))
    }

    return $parts
}

function Invoke-BotProcess {
    Param([string[]]$CommandParts)
    $proc = Start-Process -FilePath $python -ArgumentList $CommandParts -Wait -PassThru -NoNewWindow
    return @{
        ExitCode = [int]$proc.ExitCode
        Pid = [int]$proc.Id
    }
}

function Get-RuntimeStatus {
    if (-not (Test-Path $runtimeStatusPath)) {
        return $null
    }
    try {
        return Get-Content -Path $runtimeStatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

$cmdParts = New-BotCommandParts
$cmdLine = "$python " + ($cmdParts -join " ")

Write-Host "Running bot with account mode: $AccountMode (ALPACA_PAPER=$env:ALPACA_PAPER)"

if (-not $Watchdog) {
    & $python @cmdParts
    exit $LASTEXITCODE
}

if ($WatchdogMaxRestarts -lt 0) {
    throw "WatchdogMaxRestarts must be >= 0"
}
if ($WatchdogBaseBackoffSeconds -lt 1) {
    throw "WatchdogBaseBackoffSeconds must be >= 1"
}
if ($WatchdogMaxBackoffSeconds -lt $WatchdogBaseBackoffSeconds) {
    throw "WatchdogMaxBackoffSeconds must be >= WatchdogBaseBackoffSeconds"
}

$runtimePreflight = Get-RuntimeStatus
if ($runtimePreflight -and [bool]$runtimePreflight.entry_lockout -and -not $AllowLockoutStart) {
    $lockoutReason = [string]$runtimePreflight.entry_lockout_reason
    if ([string]::IsNullOrWhiteSpace($lockoutReason)) {
        $lockoutReason = "Runtime status reports active entry lockout."
    }
    Write-WatchdogState -Status "blocked_preflight_lockout" -RestartCount 0 -LastExitCode 3 -Command $cmdLine -Message "Watchdog start blocked by active entry lockout. Use -AllowLockoutStart to override." -NextRestartAt $null
    Write-WatchdogLog "Watchdog preflight blocked by entry lockout. Reason: $lockoutReason"
    Send-DiscordNotification -EventName "watchdog_stop" -Title "Watchdog Preflight Blocked" -Message "Active entry lockout blocked watchdog start. Reason: $lockoutReason"
    Write-Host "[ERR] Watchdog start blocked by active entry lockout. Use -AllowLockoutStart to override." -ForegroundColor Red
    exit 3
}

Write-Host "Watchdog mode enabled (max restarts: $WatchdogMaxRestarts, backoff: $WatchdogBaseBackoffSeconds-$WatchdogMaxBackoffSeconds s)."
Write-WatchdogLog "Watchdog started | command=$cmdLine"

$restartCount = 0
$lastExitCode = 0

while ($true) {
    if (Test-Path $watchdogStopFlagPath) {
        Write-WatchdogState -Status "stopped_by_flag" -RestartCount $restartCount -LastExitCode $lastExitCode -Command $cmdLine -Message "Stop flag detected." -NextRestartAt $null
        Write-WatchdogLog "Stop flag detected. Watchdog exiting."
        Send-DiscordNotification -EventName "watchdog_stop" -Title "Watchdog Stopped" -Message "Stop flag detected; watchdog exiting."
        exit 0
    }

    Write-WatchdogState -Status "running" -RestartCount $restartCount -LastExitCode $lastExitCode -Command $cmdLine -Message "Launching bot process." -NextRestartAt $null
    Write-WatchdogLog "Launching bot process (restart_count=$restartCount)."

    try {
        $result = Invoke-BotProcess -CommandParts $cmdParts
        $lastExitCode = [int]$result.ExitCode
    } catch {
        $lastExitCode = 1
        Write-WatchdogLog "Process launch failed: $($_.Exception.Message)"
    }

    $runtimeStatus = Get-RuntimeStatus
    if ($runtimeStatus -and $runtimeStatus.status -eq "halted") {
        $haltReason = [string]$runtimeStatus.halt_reason
        if ([string]::IsNullOrWhiteSpace($haltReason)) {
            $haltReason = "Runtime reported halted status"
        }
        $finalExitCode = if ($lastExitCode -eq 0) { 2 } else { $lastExitCode }
        Write-WatchdogState -Status "halted_runtime_breaker" -RestartCount $restartCount -LastExitCode $finalExitCode -Command $cmdLine -Message "Bot halted by circuit breaker; watchdog will not restart." -NextRestartAt $null
        Write-WatchdogLog "Runtime status is halted. Watchdog stopping restarts. Reason: $haltReason"
        Send-DiscordNotification -EventName "watchdog_stop" -Title "Watchdog Paused By Circuit Breaker" -Message "Watchdog will not restart. Reason: $haltReason"
        exit $finalExitCode
    }

    if ($lastExitCode -eq 0) {
        Write-WatchdogState -Status "exited_cleanly" -RestartCount $restartCount -LastExitCode $lastExitCode -Command $cmdLine -Message "Bot exited with code 0." -NextRestartAt $null
        Write-WatchdogLog "Bot exited cleanly (exit_code=0)."
        Send-DiscordNotification -EventName "watchdog_stop" -Title "Watchdog Exited Cleanly" -Message "Bot exited with code 0."
        exit 0
    }

    $restartCount += 1
    if ($restartCount -gt $WatchdogMaxRestarts) {
        Write-WatchdogState -Status "halted_max_restarts" -RestartCount $restartCount -LastExitCode $lastExitCode -Command $cmdLine -Message "Maximum restart limit reached." -NextRestartAt $null
        Write-WatchdogLog "Maximum restart limit reached. Halting watchdog (last_exit_code=$lastExitCode)."
        Send-DiscordNotification -EventName "watchdog_stop" -Title "Watchdog Max Restarts Reached" -Message "Watchdog halted after max restarts. Last exit code: $lastExitCode"
        exit $lastExitCode
    }

    $backoffSeconds = [Math]::Min(
        $WatchdogMaxBackoffSeconds,
        [int]($WatchdogBaseBackoffSeconds * [Math]::Pow(2, $restartCount - 1))
    )
    $nextRestart = (Get-Date).AddSeconds($backoffSeconds)

    Write-WatchdogState -Status "restarting" -RestartCount $restartCount -LastExitCode $lastExitCode -Command $cmdLine -Message "Restarting after failure with backoff." -NextRestartAt $nextRestart
    Write-WatchdogLog "Bot exited with code $lastExitCode. Restarting in $backoffSeconds second(s) (attempt $restartCount/$WatchdogMaxRestarts)."
    Send-DiscordNotification -EventName "watchdog_restart" -Title "Watchdog Restart" -Message "Exit code $lastExitCode. Restarting in $backoffSeconds second(s) (attempt $restartCount/$WatchdogMaxRestarts)."
    Start-Sleep -Seconds $backoffSeconds
}
