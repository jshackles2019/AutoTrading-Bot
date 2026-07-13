Param(
    [int]$Port = 8501,
    [string]$Address = "tailscale",
    [switch]$Headless
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$python = "C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$resolvedAddress = $Address
if ([string]::IsNullOrWhiteSpace($resolvedAddress) -or $resolvedAddress -in @("auto", "tailscale")) {
    $resolvedAddress = $null
    $tailscaleCommand = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($tailscaleCommand) {
        try {
            $tailscaleExecutable = if ($tailscaleCommand.Path) { $tailscaleCommand.Path } else { $tailscaleCommand.Name }
            $resolvedAddress = (& $tailscaleExecutable ip -4 | Select-Object -First 1).Trim()
        }
        catch {
            $resolvedAddress = $null
        }
    }

    if ([string]::IsNullOrWhiteSpace($resolvedAddress)) {
        $resolvedAddress = "127.0.0.1"
        Write-Warning "Tailscale IP not available. Falling back to local-only binding at 127.0.0.1."
    }
}

$streamlitArgs = @("-m", "streamlit", "run", "ui/Home.py", "--server.address", "$resolvedAddress", "--server.port", "$Port")
if ($Headless) {
    $streamlitArgs += @("--server.headless", "true")
}

Write-Host "Starting Streamlit UI on $resolvedAddress`:$Port..."
& $python @streamlitArgs
