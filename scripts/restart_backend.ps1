param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1",
    [string]$ApiKey = "super_secure_api_key",
    [int]$StartupTimeoutSec = 30,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $repoRoot "logs"
$outLog = Join-Path $logsDir ("backend{0}.out.log" -f $Port)
$errLog = Join-Path $logsDir ("backend{0}.err.log" -f $Port)

Set-Location $repoRoot

if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

function Get-PythonExecutable {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return 'python'
    }

    $venvPython = Join-Path $repoRoot 'venv\Scripts\python.exe'
    if (Test-Path $venvPython) {
        return $venvPython
    }

    throw 'No Python executable found for backend startup.'
}

function Test-BackendHealth {
    param(
        [int]$HealthPort,
        [string]$HealthApiKey
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/health/live" -f $HealthPort) -Headers @{ "x-api-key" = $HealthApiKey } -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-BackendOnPort {
    param([int]$TargetPort)

    $listeners = @(Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Sort-Object OwningProcess -Unique)
    foreach ($listener in $listeners) {
        $candidateIds = New-Object System.Collections.Generic.List[int]
        $candidateIds.Add([int]$listener.OwningProcess)

        $processInfo = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $listener.OwningProcess) -ErrorAction SilentlyContinue
        if ($processInfo -and $processInfo.ParentProcessId) {
            $parentInfo = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $processInfo.ParentProcessId) -ErrorAction SilentlyContinue
            if ($parentInfo -and $parentInfo.Name -like "uvicorn*") {
                $candidateIds.Add([int]$parentInfo.ProcessId)
            }
        }

        foreach ($processId in ($candidateIds | Sort-Object -Unique)) {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

$pythonExe = Get-PythonExecutable

if (-not $ForceRestart -and (Test-BackendHealth -HealthPort $Port -HealthApiKey $ApiKey)) {
    Write-Output ("Backend already healthy on port {0}." -f $Port)
    exit 0
}

Stop-BackendOnPort -TargetPort $Port
Start-Sleep -Milliseconds 500

$startArgs = @{
    FilePath = $pythonExe
    ArgumentList = @('-m', 'uvicorn', 'backend.main:app', '--host', $BindHost, '--port', [string]$Port)
    WorkingDirectory = $repoRoot
    PassThru = $true
    RedirectStandardOutput = $outLog
    RedirectStandardError = $errLog
}
$serverProcess = Start-Process @startArgs

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-BackendHealth -HealthPort $Port -HealthApiKey $ApiKey) {
        Write-Output ("Backend healthy on http://{0}:{1} (PID {2}) using {3}." -f $BindHost, $Port, $serverProcess.Id, $pythonExe)
        exit 0
    }
    Start-Sleep -Seconds 1
}

Write-Error ("Backend failed to become healthy on port {0}. See {1} and {2}." -f $Port, $outLog, $errLog)
