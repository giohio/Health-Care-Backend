"""Pytest bootstrap for Payment Service unit tests."""

import os
import sys
from pathlib import Path


service_root = Path(__file__).resolve().parent.parent
workspace_root = service_root.parent

shared_paths = [
    workspace_root / "shared" / "healthai-db",
    workspace_root / "shared" / "healthai-events",
    workspace_root / "shared" / "healthai-cache",
    workspace_root / "shared" / "healthai-common",
]

# Ensure imports resolve to this service first.
sys.path.insert(0, str(service_root))
for shared in shared_paths:
    if shared.exists():
        sys.path.insert(0, str(shared))

os.environ["PYTHONPATH"] = os.pathsep.join(sys.path)
