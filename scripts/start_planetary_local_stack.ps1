param(
    [int]$BackendPort = 8002,
    [int]$FrontendPort = 5174,
    [int]$RuntimeIntervalSeconds = 300,
    [int]$SourceRefreshIntervalSeconds = 900,
    [int]$BacktestIntervalSeconds = 21600,
    [switch]$ForceRestart,
    [switch]$WarmMaterialize = $true
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$backendScript = Join-Path $PSScriptRoot "restart_backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "restart_frontend.ps1"
$schedulerScript = Join-Path $PSScriptRoot "restart_planetary_runtime_scheduler.ps1"

if (-not (Test-Path $backendScript)) { throw "Missing backend restart script at $backendScript" }
if (-not (Test-Path $frontendScript)) { throw "Missing frontend restart script at $frontendScript" }
if (-not (Test-Path $schedulerScript)) { throw "Missing scheduler restart script at $schedulerScript" }

& $backendScript -Port $BackendPort -BindHost "127.0.0.1" -ForceRestart:$ForceRestart
& $frontendScript -Port $FrontendPort -BindHost "127.0.0.1" -ForceRestart:$ForceRestart
& $schedulerScript `
    -IntervalSeconds $RuntimeIntervalSeconds `
    -SourceRefreshIntervalSeconds $SourceRefreshIntervalSeconds `
    -BacktestIntervalSeconds $BacktestIntervalSeconds `
    -ForceRestart:$ForceRestart

$pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

if ($WarmMaterialize) {
    & $pythonExe "scripts/run_planetary_runtime_materialize.py" --run-backtests | Out-Null
}

Write-Output ("Planetary local stack ready. Frontend: http://127.0.0.1:{0} | Backend: http://127.0.0.1:{1}" -f $FrontendPort, $BackendPort)
