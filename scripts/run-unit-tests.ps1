param(
    [switch]$PaymentOnly,
    [switch]$NotificationOnly,
    [switch]$AppointmentOnly,
    [switch]$AuthOnly,
    [switch]$DoctorOnly,
    [switch]$PatientOnly
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
        $env:PYTHONPATH = "$sharedDb;$sharedEvents;$sharedCache;$sharedCommon;$($env:PYTHONPATH)"
        & "$PSScriptRoot\..\.venv\Scripts\python.exe" -m pytest $Target -q
    }
    finally {
        Pop-Location
    }
}

if ((@($PaymentOnly, $NotificationOnly, $AppointmentOnly, $AuthOnly, $DoctorOnly, $PatientOnly) | Where-Object { $_ }).Count -gt 1) {
    throw "Use only one of -PaymentOnly, -NotificationOnly, -AppointmentOnly, -AuthOnly, -DoctorOnly or -PatientOnly"
}

if ($PaymentOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Payment Service" -Target "tests/unit"
    exit 0
}

if ($NotificationOnly) {
    Run-ServiceTests -ServicePath "$PSScriptRoot\..\Notifiaction Service" -Target "tests/unit"
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

Run-ServiceTests -ServicePath "$PSScriptRoot\..\Payment Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Notifiaction Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Appointment Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Auth service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Doctor Service" -Target "tests/unit"
Run-ServiceTests -ServicePath "$PSScriptRoot\..\Patient Service" -Target "tests/unit"
