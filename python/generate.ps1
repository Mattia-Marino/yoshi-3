<#
PowerShell script to generate Python gRPC code from proto files
Usage: .\generate.ps1
#>

$ErrorActionPreference = 'Stop'

Write-Host "Generating gRPC Python code..." -ForegroundColor Cyan

# Ensure we're running from the script directory
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

# Create generated directory if it doesn't exist
New-Item -ItemType Directory -Force -Path "generated" | Out-Null

# Path to proto
$proto = "./protos/processor.proto"

try {
    & python -m grpc_tools.protoc --proto_path=./protos --python_out=./generated --grpc_python_out=./generated $proto
    if ($LASTEXITCODE -ne 0) { throw "protoc failed with exit code $LASTEXITCODE" }
} catch {
    Write-Host "Error running protoc: $_" -ForegroundColor Red
    exit 1
}

# Ensure __init__.py exists so generated is a package
if (-not (Test-Path -Path "generated\__init__.py")) {
    "" | Out-File -FilePath "generated\__init__.py" -Encoding utf8
}

Write-Host "Generated files created in ./generated/" -ForegroundColor Green
Write-Host "processor_pb2.py" -ForegroundColor Green
Write-Host "processor_pb2_grpc.py" -ForegroundColor Green