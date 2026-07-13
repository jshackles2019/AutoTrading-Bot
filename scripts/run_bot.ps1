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
    [double]$VolumeRatioCap
)

$requiredLiveToken = "LIVE-TRADE-YES"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

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

$cmdParts = @("src/main.py")
if ($SmokeTest) {
    $cmdParts += "--smoke-test"
} else {
    if ($DryRun) { $cmdParts += "--dry-run" }
    if ($SkipMarketCheck) { $cmdParts += "--skip-market-check" }
    if ($PSBoundParameters.ContainsKey("MaxLoops")) {
        if ($MaxLoops -lt 1) {
            throw "MaxLoops must be >= 1"
        }
        $cmdParts += @("--max-loops", "$MaxLoops")
    }
    if ($SymbolUniverse -ne "config") {
        $cmdParts += @("--symbol-universe", $SymbolUniverse)
        if ($PSBoundParameters.ContainsKey("MaxSymbols")) {
            $cmdParts += @("--max-symbols", "$MaxSymbols")
        }
        if ($PSBoundParameters.ContainsKey("ScanSelection")) {
            $cmdParts += @("--scan-selection", $ScanSelection)
        }
    }
    if ($Symbols) {
        $symbolsCsv = ($Symbols -join ",")
        $cmdParts += @("--symbols", $symbolsCsv)
        if ($AppendSymbols) {
            $cmdParts += "--append-symbols"
        }
    }
    if ($PSBoundParameters.ContainsKey("TopCandidates")) {
        $cmdParts += @("--top-candidates", "$TopCandidates")
    }
    if ($PSBoundParameters.ContainsKey("MinPrice")) {
        $cmdParts += @("--min-price", "$MinPrice")
    }
    if ($PSBoundParameters.ContainsKey("MaxPrice")) {
        $cmdParts += @("--max-price", "$MaxPrice")
    }
    if ($PSBoundParameters.ContainsKey("MinAverageVolume")) {
        $cmdParts += @("--min-average-volume", "$MinAverageVolume")
    }
    if ($PSBoundParameters.ContainsKey("WeightConfidence")) {
        $cmdParts += @("--weight-confidence", "$WeightConfidence")
    }
    if ($PSBoundParameters.ContainsKey("WeightBreakout")) {
        $cmdParts += @("--weight-breakout", "$WeightBreakout")
    }
    if ($PSBoundParameters.ContainsKey("WeightVolume")) {
        $cmdParts += @("--weight-volume", "$WeightVolume")
    }
    if ($PSBoundParameters.ContainsKey("WeightMomentum")) {
        $cmdParts += @("--weight-momentum", "$WeightMomentum")
    }
    if ($PSBoundParameters.ContainsKey("VolumeRatioCap")) {
        $cmdParts += @("--volume-ratio-cap", "$VolumeRatioCap")
    }
}

Write-Host "Running bot with account mode: $AccountMode (ALPACA_PAPER=$env:ALPACA_PAPER)"
& $python @cmdParts
