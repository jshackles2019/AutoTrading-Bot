Param(
    [switch]$List,
    [switch]$Kill,
    [string]$ProcessName = "python.exe",
    [switch]$IncludeCurrent
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$selfPid = $PID
$trackedStateFiles = @(
    (Join-Path $repoRoot "data\ui\background_runner.json"),
    (Join-Path $repoRoot "data\ui\active_bot_process.json")
)

if (-not $List -and -not $Kill) {
    $List = $true
}

$candidates = Get-CimInstance Win32_Process -Filter "Name = '$ProcessName'" |
    Where-Object {
        $cmd = $_.CommandLine
        -not [string]::IsNullOrWhiteSpace($cmd) -and $cmd -like "*$repoRoot*"
    }

if (-not $IncludeCurrent) {
    $candidates = $candidates | Where-Object { $_.ProcessId -ne $selfPid }
}

$trackedPids = @()
foreach ($stateFile in $trackedStateFiles) {
    if (Test-Path $stateFile) {
        try {
            $state = Get-Content -Raw $stateFile | ConvertFrom-Json
            if ($state.pid) {
                $trackedPids += [int]$state.pid
            }
        } catch {
            Write-Warning "Could not parse state file: $stateFile"
        }
    }
}

foreach ($pid in ($trackedPids | Sort-Object -Unique)) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid"
        if ($proc -and $proc.Name -eq $ProcessName) {
            if (-not $IncludeCurrent -and $proc.ProcessId -eq $selfPid) {
                continue
            }
            if (-not ($candidates | Where-Object { $_.ProcessId -eq $proc.ProcessId })) {
                $candidates += $proc
            }
        }
    } catch {}
}

if ($List) {
    if (-not $candidates) {
        Write-Host "No repo-scoped $ProcessName processes found."
    } else {
        Write-Host "Repo-scoped $ProcessName processes:"
        $candidates |
            Select-Object ProcessId, Name, CommandLine |
            Sort-Object ProcessId |
            Format-Table -AutoSize
    }
}

if ($Kill) {
    if (-not $candidates) {
        Write-Host "No repo-scoped $ProcessName processes to kill."
        return
    }

    foreach ($proc in $candidates) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped PID $($proc.ProcessId)"
        } catch {
            Write-Warning "Failed to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}
