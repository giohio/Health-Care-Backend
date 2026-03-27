param(
    [switch]$PaymentOnly,
    [switch]$NotificationOnly,
    [switch]$AppointmentOnly,
    [switch]$AuthOnly,
    [switch]$DoctorOnly,
    [switch]$PatientOnly,
    [switch]$NewFeaturesOnly,
    [switch]$Coverage
)

$ErrorActionPreference = "Stop"

function Run-ServiceTests {
    param(
        [string]$ServicePath,
        [string]$Target
    )

    Push-Location $ServicePath
    try {
        $sharedDb = (Resolve-Path "$PSScriptRoot\..\shared\healthai-db").Path
        $sharedEvents = (Resolve-Path "$PSScriptRoot\..\shared\healthai-events").Path
        $sharedCache = (Resolve-Path "$PSScriptRoot\..\shared\healthai-cache").Path
        $sharedCommon = (Resolve-Path "$PSScriptRoot\..\shared\healthai-common").Path
        $sharedTracing = (Resolve-Path "$PSScriptRoot\..\shared\healthai-tracing").Path
        $env:PYTHONPATH = "$sharedDb;$sharedEvents;$sharedCache;$sharedCommon;$sharedTracing"
        & "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest $Target -q --tb=short
    }
    finally {
        Pop-Location
    }
}

if ((@($PaymentOnly, $NotificationOnly, $AppointmentOnly, $AuthOnly, $DoctorOnly, $PatientOnly, $NewFeaturesOnly) | Where-Object { $_ }).Count -gt 1) {
    throw "Use only one of -PaymentOnly, -NotificationOnly, -AppointmentOnly, -AuthOnly, -DoctorOnly, -PatientOnly or -NewFeaturesOnly"
}

function Run-CoverageReport {
    param(
        [string]$ServicePath,
        [string]$ServiceName,
        [string]$Target = "tests/unit"
    )

    Push-Location $ServicePath
    try {
        $sharedDb = (Resolve-Path "$PSScriptRoot\..\shared\healthai-db").Path
        $sharedEvents = (Resolve-Path "$PSScriptRoot\..\shared\healthai-events").Path
        $sharedCache = (Resolve-Path "$PSScriptRoot\..\shared\healthai-cache").Path
        $sharedCommon = (Resolve-Path "$PSScriptRoot\..\shared\healthai-common").Path
        $sharedTracing = (Resolve-Path "$PSScriptRoot\..\shared\healthai-tracing").Path
        $env:PYTHONPATH = "$sharedDb;$sharedEvents;$sharedCache;$sharedCommon;$sharedTracing"
        Write-Host "Coverage for ${ServiceName}:" -ForegroundColor Cyan
        & "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest $Target --cov=Application --cov=Domain --cov=infrastructure --cov-report=term-missing -q --tb=short
    }
    finally {
        Pop-Location
    }
}

if ($PaymentOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Payment Service" -Target "tests/unit"
    exit 0
}

if ($NotificationOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Notification Service" -Target "tests/unit"
    exit 0
}

if ($AppointmentOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Appointment Service" -Target "tests/unit"
    exit 0
}

if ($AuthOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Auth service" -Target "tests/unit"
    exit 0
}

if ($DoctorOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Doctor Service" -Target "tests/unit"
    exit 0
}

if ($PatientOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Patient Service" -Target "tests/unit"
    exit 0
}

if ($NewFeaturesOnly) {
    Write-Host "Running new feature tests (21 core use case tests)..." -ForegroundColor Green
    
    # Use case tests (21 tests - PROVEN WORKING)
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Patient Service" -Target "tests/unit/test_vitals_and_health_summary_use_cases.py"
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Doctor Service" -Target "tests/unit/test_new_schedule_dayoff_service_rating_use_cases.py"
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Appointment Service" -Target "tests/unit/test_new_start_stats_internal_use_cases.py"
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Notification Service" -Target "tests/unit/test_new_unread_consumer_scheduler_use_cases.py"
    
    exit 0
}

if ($Coverage) {
    Write-Host "Running coverage report for all services..." -ForegroundColor Green
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Payment Service" -ServiceName "Payment Service"
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Notification Service" -ServiceName "Notification Service"
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Appointment Service" -ServiceName "Appointment Service"
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Auth service" -ServiceName "Auth Service"
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Doctor Service" -ServiceName "Doctor Service"
    Run-CoverageReport -ServicePath "$PSScriptRoot\..\Patient Service" -ServiceName "Patient Service"
    exit 0
}

Run-ServiceTests -ServicePath "$PSScriptRoot\..\Payment Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Notification Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Appointment Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Auth service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Doctor Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Patient Service" -Target "tests/unit"
