param(
    [int]$MinCoverage = 85
)

$ErrorActionPreference = "Stop"

$services = @(
    "Payment Service",
    "Notifiaction Service",
    "Appointment Service",
    "Auth service",
    "Doctor Service",
    "Patient Service"
)

$pythonExe = "$PSScriptRoot\..\.venv\Scripts\python.exe"
$sharedDb = (Resolve-Path "$PSScriptRoot\..\shared\healthai-db").Path
$sharedEvents = (Resolve-Path "$PSScriptRoot\..\shared\healthai-events").Path
$sharedCache = (Resolve-Path "$PSScriptRoot\..\shared\healthai-cache").Path
$sharedCommon = (Resolve-Path "$PSScriptRoot\..\shared\healthai-common").Path

foreach ($service in $services) {
    Write-Host "`n=== $service (cov>=$MinCoverage) ==="
    Push-Location "$PSScriptRoot\..\$service"
    try {
        $env:PYTHONPATH = "$sharedDb;$sharedEvents;$sharedCache;$sharedCommon;$($env:PYTHONPATH)"
        & $pythonExe -m pytest tests/unit --cov=Application --cov-report=term-missing --cov-fail-under=$MinCoverage -q
    }
    finally {
        Pop-Location
    }
}
