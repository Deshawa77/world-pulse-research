param(
    [int]$Port = 5174,
    [string]$BindHost = "127.0.0.1",
    [int]$StartupTimeoutSec = 45,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "world-pulse-frontend"
$outLog = Join-Path $repoRoot ("frontend{0}.current.out.log" -f $Port)
$errLog = Join-Path $repoRoot ("frontend{0}.current.err.log" -f $Port)

function Get-NpmExecutable {
    $candidates = @("npm.cmd", "npm")
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "npm executable not found for frontend startup."
}

function Test-FrontendHealth {
    param(
        [string]$Host,
        [int]$TargetPort
    )
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://{0}:{1}/" -f $Host, $TargetPort) -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Stop-FrontendOnPort {
    param([int]$TargetPort)
    $listeners = @(Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue | Sort-Object OwningProcess -Unique)
    foreach ($listener in $listeners) {
        Stop-Process -Id ([int]$listener.OwningProcess) -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $frontendRoot)) {
    throw "Frontend root not found at $frontendRoot"
}

if (-not $ForceRestart -and (Test-FrontendHealth -Host $BindHost -TargetPort $Port)) {
    Write-Output ("Frontend already healthy on http://{0}:{1}/." -f $BindHost, $Port)
    exit 0
}

Stop-FrontendOnPort -TargetPort $Port
Start-Sleep -Milliseconds 500

$npmExe = Get-NpmExecutable
$startArgs = @{
    FilePath = $npmExe
    ArgumentList = @("run", "dev", "--", "--host", $BindHost, "--port", [string]$Port)
    WorkingDirectory = $frontendRoot
    PassThru = $true
    RedirectStandardOutput = $outLog
    RedirectStandardError = $errLog
    WindowStyle = "Hidden"
}
$serverProcess = Start-Process @startArgs

$deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-FrontendHealth -Host $BindHost -TargetPort $Port) {
        Write-Output ("Frontend healthy on http://{0}:{1}/ (PID {2}) using {3}." -f $BindHost, $Port, $serverProcess.Id, $npmExe)
        exit 0
    }
    Start-Sleep -Seconds 1
}

Write-Error ("Frontend failed to become healthy on port {0}. See {1} and {2}." -f $Port, $outLog, $errLog)
