"""
Pytest configuration for Doctor Service unit tests.
This ensures the service's Application and Domain modules are importable.
"""

import os
import sys
from pathlib import Path

# Get the service root directory (two levels up from this file)
service_root = Path(__file__).parent.parent.parent

# Set PYTHONPATH to include this service directory
# This allows imports like "from Application..." to resolve correctly
service_root_str = str(service_root)
if service_root_str not in sys.path:
    sys.path.insert(0, service_root_str)

# Also set the environment variable for subprocess calls
os.environ["PYTHONPATH"] = service_root_str + os.pathsep + os.environ.get("PYTHONPATH", "")
