# ==========================================
# STAGE 1: Builder — install dependencies only
# Using python:3.10-slim keeps base image lightweight
# ==========================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build-time system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency installation
RUN pip install --no-cache-dir uv

# Copy only dependency files first
COPY ["Patient Service/requirements.txt", "."]
RUN uv pip install --system --no-cache -r requirements.txt

# Install shared packages used across services
COPY shared /tmp/shared
RUN uv pip install --system --no-cache /tmp/shared/healthai-cache \
    && uv pip install --system --no-cache /tmp/shared/healthai-common \
    && uv pip install --system --no-cache /tmp/shared/healthai-db \
    && uv pip install --system --no-cache /tmp/shared/healthai-events

# ==========================================
# STAGE 2: Runtime — minimal production image
# ==========================================
FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

# Install runtime OS packages and setup security
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && groupadd -r appuser && useradd -r -g appuser appuser \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code and setup permissions
COPY ["Patient Service/", "."]
COPY shared/healthai-tracing /shared/healthai-tracing
RUN chmod +x scripts/entrypoint.sh && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Port (Patient Service uses 8000)
EXPOSE 8000

# Health check (assuming it listens on 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint
ENTRYPOINT ["/bin/sh", "/app/scripts/entrypoint.sh"]

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
