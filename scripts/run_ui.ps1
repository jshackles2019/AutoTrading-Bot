Param(
    [int]$Port = 8501,
    [string]$Address = "0.0.0.0",
    [switch]$Headless
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$python = "C:/Users/John/AppData/Local/Python/pythoncore-3.14-64/python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$args = @("-m", "streamlit", "run", "ui/app.py", "--server.address", "$Address", "--server.port", "$Port")
if ($Headless) {
    $args += @("--server.headless", "true")
}

Write-Host "Starting Streamlit UI on $Address`:$Port..."
& $python @args
