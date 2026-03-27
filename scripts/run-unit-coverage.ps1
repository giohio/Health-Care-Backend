param(
    [int]$MinCoverage = 85
)

$ErrorActionPreference = "Stop"

$services = @(
    "Auth service",
    "Appointment Service",
    "Doctor Service",
    "Patient Service",
    "Payment Service",
    "Notification Service"
)

$pythonExe = "$PSScriptRoot\..\.venv\Scripts\python.exe"
$basePath = (Resolve-Path "$PSScriptRoot\..").Path
$sharedDb = Join-Path $basePath "shared\healthai-db"
$sharedEvents = Join-Path $basePath "shared\healthai-events"
$sharedCache = Join-Path $basePath "shared\healthai-cache"
$sharedCommon = Join-Path $basePath "shared\healthai-common"
$sharedTracing = Join-Path $basePath "shared\healthai-tracing"

$fullPythonPath = "$sharedDb;$sharedEvents;$sharedCache;$sharedCommon;$sharedTracing"

# Save original PYTHONPATH to restore later if needed
$originalPythonPath = $env:PYTHONPATH

foreach ($service in $services) {
    Write-Host "`n=== $service (cov>=$MinCoverage) ==="
    $servicePath = Join-Path $basePath $service
    Push-Location $servicePath
    try {
        # ISOLATE: Set PYTHONPATH only for this service + shared libs
        $env:PYTHONPATH = "$servicePath;$fullPythonPath"
        & $pythonExe -m pytest tests/unit --cov=Application --cov=Domain --cov=infrastructure --cov=presentation --cov-report=term-missing --cov-fail-under=$MinCoverage -q
    }
    catch {
        Write-Warning "Tests failed for $service"
    }
    finally {
        Pop-Location
        # Restore or keep clean for next iteration
        $env:PYTHONPATH = $originalPythonPath
    }
}

# Run shared tests
Write-Host "`n=== shared libs (cov>=$MinCoverage) ==="
Push-Location $basePath
try {
    $env:PYTHONPATH = "$fullPythonPath;$($env:PYTHONPATH)"
    & $pythonExe -m pytest shared --cov=shared --cov-report=term-missing --cov-fail-under=$MinCoverage -q
}
catch {
    Write-Warning "Tests failed for shared"
}
finally {
    Pop-Location
}
