"""
Root conftest.py for AI Service tests.

Sets environment variables BEFORE pydantic-settings loads them so tests
can run in CI without a real .env file.

If the .env file already exists (local dev), it takes priority via
pydantic-settings' env_file loading, UNLESS the caller explicitly sets
the env vars — which is fine for CI.
"""

import os

# Set fallback values for required settings so that pydantic-settings
# doesn't raise ValidationError when running in CI without a .env file.
# Real values in .env take precedence when the file exists (local dev).
# These must be set BEFORE any test module imports infrastructure code.
os.environ.setdefault("GROQ_API_KEY", "ci-test-placeholder-groq-key")
os.environ.setdefault("GEMINI_API_KEY", "ci-test-placeholder-gemini-key")
os.environ.setdefault("CLINICAL_SERVICE_URL", "http://clinical_service:8000")
os.environ.setdefault("EMR_RESULT_SERVICE_URL", "http://emr_result_service:8000")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
