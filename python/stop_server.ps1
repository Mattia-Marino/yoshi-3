<#
PowerShell script to stop the gRPC server
Usage: .\stop_server.ps1
#>

$ErrorActionPreference = 'Stop'

Write-Host "Stopping gRPC server..." -ForegroundColor Cyan

if ($PSScriptRoot) { Set-Location $PSScriptRoot }

# Find python app.py processes
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'python' -and $_.CommandLine -match 'app.py' }
if ($procs) {
    Write-Host "Stopping gRPC server..." -ForegroundColor Green
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Host "Failed to stop PID $($p.ProcessId): $_" -ForegroundColor Red
        }
    }
    Start-Sleep -Seconds 1
    $still = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'python' -and $_.CommandLine -match 'app.py' }
    if (-not $still) {
        Write-Host "Server stopped" -ForegroundColor Green
    } else {
        Write-Host "Failed to stop server" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "Server is not running" -ForegroundColor Yellow
}
