param(
    [int]$IntervalSeconds = 300,
    [int]$SourceRefreshIntervalSeconds = 900,
    [int]$BacktestIntervalSeconds = 21600,
    [int]$StartupTimeoutSec = 10,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $repoRoot "logs"
$outLog = Join-Path $logsDir "planetary-runtime-scheduler.out.log"
$errLog = Join-Path $logsDir "planetary-runtime-scheduler.err.log"

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

function Get-PythonExecutable {
    $localVenvCandidates = @(
        (Join-Path $repoRoot '.venv\Scripts\python.exe'),
        (Join-Path $repoRoot 'venv\Scripts\python.exe')
    )
    foreach ($candidate in $localVenvCandidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }
    throw 'No Python executable found for scheduler startup.'
}

function Stop-ExistingScheduler {
    $targets = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^python' -and $_.CommandLine -like '*scripts\run_planetary_runtime_scheduler.py*'
    })
    foreach ($processInfo in $targets) {
        Stop-Process -Id ([int]$processInfo.ProcessId) -Force -ErrorAction SilentlyContinue
    }
}

function Test-SchedulerRunning {
    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match '^python' -and $_.CommandLine -like '*scripts\run_planetary_runtime_scheduler.py*'
        }
    ).Count -gt 0
}

if (-not $ForceRestart -and (Test-SchedulerRunning)) {
    Write-Output "Planetary runtime scheduler already running."
    exit 0
}

Stop-ExistingScheduler
Start-Sleep -Milliseconds 500

$pythonExe = Get-PythonExecutable
$startArgs = @{
    FilePath = $pythonExe
    ArgumentList = @(
        "scripts/run_planetary_runtime_scheduler.py",
        "--interval-seconds", [string][Math]::Max(60, $IntervalSeconds),
        "--source-refresh-interval-seconds", [string][Math]::Max(300, $SourceRefreshIntervalSeconds),
        "--backtest-interval-seconds", [string][Math]::Max(900, $BacktestIntervalSeconds)
    )
    WorkingDirectory = $repoRoot
    PassThru = $true
    RedirectStandardOutput = $outLog
    RedirectStandardError = $errLog
    WindowStyle = "Hidden"
}
$process = Start-Process @startArgs

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Write-Output ("Planetary runtime scheduler running (PID {0}) using {1}." -f $process.Id, $pythonExe)
        exit 0
    }
    Start-Sleep -Seconds 1
}

Write-Error ("Planetary runtime scheduler failed to stay running. See {0} and {1}." -f $outLog, $errLog)
