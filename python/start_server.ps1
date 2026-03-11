<#
PowerShell script to start the gRPC server
Usage: .\start_server.ps1 [-Foreground]
#>

$ErrorActionPreference = 'Stop'

param(
    [switch]$Foreground
)

Write-Host "Starting gRPC server..." -ForegroundColor Cyan

if ($PSScriptRoot) { Set-Location $PSScriptRoot }

# Activate virtual environment if present
if (Test-Path -Path ".venv") {
    if (-not $env:VIRTUAL_ENV) {
        Write-Host "Activating virtual environment..." -ForegroundColor Cyan
        $activate = Join-Path -Path ".venv" -ChildPath "Scripts\Activate.ps1"
        if (Test-Path $activate) {
            try {
                & $activate
                Write-Host "Virtual environment activated" -ForegroundColor Green
            } catch {
                Write-Host "Failed to activate virtual environment: $_" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Activation script not found at $activate" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Virtual environment already active" -ForegroundColor Green
    }
}

# Check if server is already running (look for python app.py in command line)
$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'python' -and $_.CommandLine -match 'app.py' }
if ($running) {
    $pids = $running | Select-Object -ExpandProperty ProcessId -Unique
    Write-Host "Server is already running. PID(s): $($pids -join ', ')" -ForegroundColor Cyan
    Write-Host "To stop: .\stop_server.ps1" -ForegroundColor Cyan
    exit 0
}

if ($Foreground) {
    Write-Host "Starting gRPC server in foreground..." -ForegroundColor Green
    & python app.py
} else {
    Write-Host "Starting gRPC server in background..." -ForegroundColor Green
    $log = Join-Path $PSScriptRoot "server.log"
    try {
        $proc = Start-Process -FilePath python -ArgumentList 'app.py' -RedirectStandardOutput $log -RedirectStandardError $log -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 1
        $check = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'python' -and $_.CommandLine -match 'app.py' }
        if ($check) {
            $pids = $check | Select-Object -ExpandProperty ProcessId -Unique
            Write-Host "Server started successfully (PID: $($pids -join ', '))" -ForegroundColor Green
            Write-Host "Logs: Get-Content server.log -Wait" -ForegroundColor Cyan
            Write-Host "Test: python test_client.py" -ForegroundColor Cyan
            Write-Host "Stop: .\stop_server.ps1" -ForegroundColor Cyan
        } else {
            Write-Host "Failed to start server" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "Error starting server: $_" -ForegroundColor Red
        exit 1
    }
}
