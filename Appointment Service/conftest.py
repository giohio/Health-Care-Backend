import sys
from pathlib import Path

# Make shared packages importable in unit test context.
# Allows imports like `from healthai_events import ...` when running tests
# from an individual service directory (e.g. pytest from Appointment Service/).
SERVICE_ROOT = Path(__file__).parent.resolve()        # D:\Health Care\microservice\Appointment Service
MONO_ROOT    = SERVICE_ROOT.parent                     # D:\Health Care\microservice
SHARED_ROOT  = MONO_ROOT / "shared"                  # D:\Health Care\microservice\shared
# Each shared package lives as a subdirectory inside shared/ (no top-level __init__.py).
# E.g. shared/healthai-events/healthai_events/__init__.py
for shared_pkg in SHARED_ROOT.iterdir():
    if shared_pkg.is_dir():
        sys.path.insert(0, str(shared_pkg))

import pytest

pytest_plugins = []
