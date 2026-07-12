Param(
    [int]$Port = 8501,
    [switch]$Headless
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$python = "C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$args = @("-m", "streamlit", "run", "ui/app.py", "--server.port", "$Port")
if ($Headless) {
    $args += @("--server.headless", "true")
}

Write-Host "Starting Streamlit UI on port $Port..."
& $python @args
